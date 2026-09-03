"""Loot discovery: current raid + M+ season + candidate items.

Namespace reality (verified 2026-09-03):
- Journal API → static-{region} namespace
- Mythic-keystone API → dynamic-{region} namespace
"""
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ..blizzard.cache import cache_key, get_cached, set_cached
from ..blizzard.client import BlizzardClient
from ..config import get_settings


@dataclass
class Encounter:
    id: int
    name: str


@dataclass
class CurrentContent:
    raid_instance_id: int
    raid_name: str
    raid_encounters: list[Encounter] = field(default_factory=list)
    mplus_season_id: int | None = None
    mplus_season_name: str | None = None
    mplus_dungeon_instance_ids: list[int] = field(default_factory=list)


RAID_MODES = {"LFR", "NORMAL", "HEROIC", "MYTHIC"}


def _is_raid(instance: dict) -> bool:
    """Raid = LFR tracked + no MYTHIC_KEYSTONE mode.

    Verified 2026-09-03 against live API: M+ dungeons always carry an
    (untracked) MYTHIC_KEYSTONE mode; raids (incl. lair raids like The
    Dreamrift) never do. Keystone Dungeons pseudo-instance has nothing tracked.
    """
    modes = {m.get("mode", {}).get("type") for m in instance.get("modes", [])}
    tracked = {m.get("mode", {}).get("type") for m in instance.get("modes", [])
               if m.get("is_tracked")}
    return "LFR" in tracked and "MYTHIC_KEYSTONE" not in modes


async def _fetch_instances(db: AsyncSession) -> list[dict]:
    """journal-instance/index with cache."""
    key = cache_key("journal-instance/index", {})
    cached = await get_cached(db, key)
    if cached is not None:
        data = cached
    else:
        client = BlizzardClient()
        data = await client.journal_instances()
        await set_cached(db, key, data, get_settings().cache_ttl_journal)
    return data["instances"]


async def detect_current_content(db: AsyncSession) -> CurrentContent:
    """Find the current raid (highest-id instance with raid modes) and
    current M+ season. No hardcoded names."""
    client = BlizzardClient()

    # --- M+ season (dynamic ns) ---
    seasons = await client.mythic_keystone_seasons()
    current = seasons.get("current_season", {})
    season_id = current.get("id")

    # --- raid detection from journal instances (static ns) ---
    instances = await _fetch_instances(db)
    raid = None
    for inst in sorted(instances, key=lambda i: i["id"], reverse=True):
        detail_key = cache_key(f"journal-instance/{inst['id']}", {})
        detail = await get_cached(db, detail_key)
        if detail is None:
            detail = await client.journal_instance(inst["id"])
            await set_cached(db, detail_key, detail, get_settings().cache_ttl_journal)
        if _is_raid(detail):
            raid = detail
            break

    content = CurrentContent(
        raid_instance_id=raid["id"] if raid else 0,
        raid_name=raid["name"] if raid else "",
        raid_encounters=[
            Encounter(e["id"], e["name"]) for e in (raid or {}).get("encounters", [])
        ],
        mplus_season_id=season_id,
    )

    if season_id:
        season = await client.mythic_keystone_season(season_id)
        content.mplus_season_name = season.get("season_name")

    return content


async def encounter_items(db: AsyncSession, encounter_id: int) -> list[dict]:
    """Items dropped by an encounter. Bare ids — bonus/track resolution elsewhere."""
    key = cache_key(f"journal-encounter/{encounter_id}", {"part": "items"})
    cached = await get_cached(db, key)
    if cached is not None:
        return cached
    client = BlizzardClient()
    enc = await client.journal_encounter(encounter_id)
    items = [
        {"item_id": it["item"]["id"], "name": it["item"]["name"]}
        for it in enc.get("items", [])
    ]
    await set_cached(db, key, items, get_settings().cache_ttl_journal)
    return items


async def item_metadata(db: AsyncSession, item_id: int) -> dict:
    """Static item data (slot, class, quality) with cache."""
    key = cache_key(f"item/{item_id}", {})
    cached = await get_cached(db, key)
    if cached is not None:
        return cached
    client = BlizzardClient()
    data = await client.item(item_id)
    await set_cached(db, key, data, get_settings().cache_ttl_item)
    return data


async def item_icon(db: AsyncSession, item_id: int) -> str | None:
    """Icon URL for an item (Blizzard media API, cached)."""
    key = cache_key(f"media/item/{item_id}", {})
    cached = await get_cached(db, key)
    data = cached
    if data is None:
        client = BlizzardClient()
        try:
            data = await client.item_media(item_id)
        except Exception:
            return None
        await set_cached(db, key, data, get_settings().cache_ttl_item)
    for asset in (data or {}).get("assets", []):
        if asset.get("key") == "icon":
            return asset.get("value")
    return None

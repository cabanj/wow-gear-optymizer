"""Character discovery + snapshot creation (Blizzard Armory)."""
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blizzard.client import BlizzardClient
from ..db.models import BlizzardAccount, Character, CharacterSnapshot


async def discover_characters(db: AsyncSession, account: BlizzardAccount) -> list[dict]:
    """Fetch /profile/user/wow, upsert characters, return full list."""
    client = BlizzardClient()
    store_tokens = {}
    if account.tokens_encrypted:
        from ..auth.blizzard_oauth import TokenStore
        store_tokens = TokenStore().decrypt(account.tokens_encrypted.encode())

    data = await client.user_wow_accounts(store_tokens)
    result = []
    for wow_account in data.get("accounts", []):
        for char in wow_account.get("characters", []):
            if char.get("level", 0) < 70:  # skip low-level alts; config later
                continue
            existing = (await db.execute(
                select(Character).where(
                    Character.region == account.region,
                    Character.realm_slug == char["realm"]["slug"],
                    Character.name == char["name"],
                )
            )).scalar_one_or_none()
            if existing is None:
                existing = Character(
                    blizzard_account_id=account.id,
                    region=account.region,
                    realm_slug=char["realm"]["slug"],
                    name=char["name"],
                    class_id=char.get("playable_class", {}).get("id"),
                    level=char.get("level"),
                    race_id=char.get("race", {}).get("id"),
                )
                db.add(existing)
                await db.flush()
            result.append({
                "id": str(existing.id),
                "name": existing.name,
                "realm": existing.realm_slug,
                "class_id": existing.class_id,
                "level": existing.level,
            })
    account.wow_accounts = data.get("accounts", [])
    await db.commit()
    return result


async def snapshot_character(
    db: AsyncSession, character: Character, account: BlizzardAccount
) -> CharacterSnapshot:
    """Pull summary+equipment+spec+talents from Armory, store as one snapshot."""
    client = BlizzardClient()
    tokens = {}
    if account.tokens_encrypted:
        from ..auth.blizzard_oauth import TokenStore
        tokens = TokenStore().decrypt(account.tokens_encrypted.encode())

    summary = await client.character_summary(tokens, character.realm_slug, character.name)
    equipment = await client.character_equipment(tokens, character.realm_slug, character.name)
    specs = await client.character_specializations(tokens, character.realm_slug, character.name)
    try:
        talents = await client.character_talents(tokens, character.realm_slug, character.name)
    except Exception:
        talents = {}  # talents can 404 for some chars; non-fatal

    # mark previous snapshots not current
    old = (await db.execute(
        select(CharacterSnapshot).where(
            CharacterSnapshot.character_id == character.id,
            CharacterSnapshot.is_current.is_(True),
        )
    )).scalars().all()
    for snap in old:
        snap.is_current = False

    snap = CharacterSnapshot(
        character_id=character.id,
        source="blizzard_armory",
        timestamp=datetime.now(timezone.utc),
        raw={"summary": summary, "equipment": equipment, "specializations": specs, "talents": talents},
        item_level=summary.get("equipped_item_level"),
        is_current=True,
    )
    db.add(snap)
    # update character denormalized fields
    character.level = summary.get("level", character.level)
    character.class_id = summary.get("character_class", {}).get("id", character.class_id)
    character.class_name = summary.get("character_class", {}).get("name", character.class_name)
    active_spec = summary.get("active_spec")
    if active_spec:
        character.active_spec_id = active_spec.get("id")
        character.active_spec_name = active_spec.get("name")
    character.media_url = (summary.get("media") or {}).get("key") or character.media_url
    await db.commit()
    return snap

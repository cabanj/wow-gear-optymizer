"""Candidate item generation: journal loot × season track policy → profileset candidates."""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .discovery import encounter_items
from .upgrade_rules import TrackPolicy


# Inventory type (Blizzard) → simc slot
INV_TO_SLOT = {
    "HEAD": "head", "SHOULDER": "shoulder", "CHEST": "chest", "BACK": "back",
    "WRIST": "wrist", "HANDS": "hands", "WAIST": "waist", "LEGS": "legs",
    "FEET": "feet", "NECK": "neck", "FINGER": "finger1", "TRINKET": "trinket1",
    "MAIN_HAND": "main_hand", "OFF_HAND": "off_hand", "TWO_HANDED": "main_hand",
    "HOLDABLE": "off_hand", "TABARD": "tabard", "SHIRT": "shirt",
}


@dataclass
class CandidateItem:
    item_id: int
    name: str
    slot: str            # canonical simc slot
    item_level: int
    bonus_ids: list[int]
    source: str          # raid | mplus
    difficulty: str      # lfr/normal/heroic/mythic (raid) or mythic (mplus)
    variant: str | None  # None | great_vault | bonus_roll
    boss_or_dungeon: str
    inventory_type: str


async def generate_candidates(
    db: AsyncSession,
    encounter_ids: dict[int, str],       # encounter_id → boss/dungeon name
    worn_items: dict[str, dict],         # slot → {item_id, item_level, bonus_ids, gems, enchant}
    policy: TrackPolicy,
    max_per_slot: int = 3,
) -> list[CandidateItem]:
    """One candidate per (item, applicable difficulty).

    Policy: raid items sim the max realistic difficulty ladder (all 4 for raid,
    capped per slot by ilvl prescreen); mplus items get vault + bonus roll only.
    """
    seen_slots: dict[str, list[CandidateItem]] = {}
    out: list[CandidateItem] = []

    for enc_id, enc_name in encounter_ids.items():
        items = await encounter_items(db, enc_id)
        for meta in items:
            item_id, name = meta["item_id"], meta["name"]
            inv_type = (await _inv_type(db, item_id)).upper()
            slot = INV_TO_SLOT.get(inv_type)
            if slot is None:
                continue

            # family slots that share loot (rings / trinkets come in pairs)
            family = [slot]
            if slot == "finger1":
                family.append("finger2")
            elif slot == "trinket1":
                family.append("trinket2")
            family_worn = [(worn_items.get(ws, {}).get("item_id"),
                            worn_items.get(ws, {}).get("item_level") or 0)
                           for ws in family]

            def owned(item_id: int, ilvl: int) -> bool:
                """Same item already worn at equal or higher ilvl — no point simming."""
                return any(wid == item_id and (wil or 0) >= ilvl
                           for wid, wil in family_worn)

            # prescreen: skip if base ilvl ladder max << worn item (configurable)
            worn_ilvl = max([wil for _, wil in family_worn] + [0])
            variants = []
            if enc_name and _is_raid_source(enc_id, encounter_ids) or True:
                pass  # source determined below

            for diff in ("lfr", "normal", "heroic", "mythic"):
                v = policy.raid_variant(item_id, diff)
                if owned(item_id, v["item_level"]):
                    continue
                # keep only variants that beat or match worn ilvl (except trinkets/rings)
                keep = v["item_level"] >= worn_ilvl or inv_type in ("TRINKET", "FINGER")
                if worn_ilvl and not keep:
                    continue
                variants.append(CandidateItem(
                    item_id=item_id, name=name, slot=slot,
                    item_level=v["item_level"], bonus_ids=v["bonus_ids"],
                    source="raid", difficulty=diff, variant=None,
                    boss_or_dungeon=enc_name, inventory_type=inv_type,
                ))
            for variant in ("great_vault", "bonus_roll"):
                v = policy.mplus_variant(item_id, variant)
                if owned(item_id, v["item_level"]):
                    continue
                if v["item_level"] >= worn_ilvl or inv_type in ("TRINKET", "FINGER"):
                    variants.append(CandidateItem(
                        item_id=item_id, name=name, slot=slot,
                        item_level=v["item_level"], bonus_ids=v["bonus_ids"],
                        source="mplus", difficulty="mythic", variant=variant,
                        boss_or_dungeon=enc_name, inventory_type=inv_type,
                    ))

            # rings/trinkets: sim each candidate against BOTH worn slots
            # (decision 2026-09-03: every trinket tried vs each equipped one)
            if slot in ("finger1", "trinket1"):
                twin = "finger2" if slot == "finger1" else "trinket2"
                variants += [CandidateItem(
                    item_id=v.item_id, name=v.name, slot=twin,
                    item_level=v.item_level, bonus_ids=v.bonus_ids,
                    source=v.source, difficulty=v.difficulty, variant=v.variant,
                    boss_or_dungeon=v.boss_or_dungeon, inventory_type=v.inventory_type,
                ) for v in list(variants)]

            # cap per slot by ilvl desc
            bucket = seen_slots.setdefault(slot, [])
            bucket.extend(variants)
            bucket.sort(key=lambda c: c.item_level, reverse=True)
            allowed = bucket[:max_per_slot]
            # rebuild out for this slot
            out = [c for c in out if c.slot != slot] + allowed

    return out


_RAID_ENCOUNTERS: set[int] = set()


def mark_raid_encounters(encounter_ids: list[int]) -> None:
    """Called by content discovery so candidates know the source type."""
    _RAID_ENCOUNTERS.clear()
    _RAID_ENCOUNTERS.update(encounter_ids)


def _is_raid_source(enc_id: int, encounter_ids: dict[int, str]) -> bool:
    return enc_id in _RAID_ENCOUNTERS


async def _inv_type(db: AsyncSession, item_id: int) -> str:
    from .discovery import item_metadata
    data = await item_metadata(db, item_id)
    return (data.get("inventory_type") or {}).get("type", "")

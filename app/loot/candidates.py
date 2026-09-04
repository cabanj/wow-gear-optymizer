"""Candidate item generation: journal loot × season track policy → profileset candidates.

Class-aware: only items the character's class can actually equip are kept
(armor type for armor pieces, weapon subclass for weapons, plus the
class-agnostic trinket/ring/neck/off-hand "Miscellaneous" subclass).
Otherwise we'd sim a warlock in agility leather / an axe it can't hold.
"""
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .discovery import encounter_items, item_metadata
from .upgrade_rules import TrackPolicy


# Inventory type (Blizzard) → canonical simc slot.
# Blizzard names vary ("Two-Hand"/"Two-handed", "One-Hand"/"Main Hand",
# "Off Hand"/"Holdable") — normalize by stripping and lowercasing.
def _slot_from_inv(inv_type: str) -> str | None:
    key = (inv_type or "").replace("_", " ").replace("-", " ").strip().lower()
    key = " ".join(key.split())  # collapse runs of spaces
    if key.startswith("two hand"):
        return "main_hand"
    if key.startswith("one hand") or key.startswith("main hand"):
        return "main_hand"
    if key.startswith("off hand") or key in ("holdable", "shield"):
        return "off_hand"
    if key and (key.startswith("range") or key.split()[0] in
                ("bow", "gun", "crossbow", "thrown")):
        return "main_hand"  # ranged weapons occupy the main hand slot
    body = key.split()[0] if key else ""
    if body in ("head", "shoulder", "chest", "wrist", "hands", "waist",
                "legs", "feet", "neck", "back", "cloak"):
        return {"back": "back", "cloak": "back"}.get(body, body)
    if body in ("finger", "ring"):
        return "finger1"
    if body == "trinket":
        return "trinket1"
    return None


INV_TO_SLOT_FN = _slot_from_inv


# Armor type (item_class=Armor, item_subclass=...) your class may wear.
CLASS_ARMOR = {
    "Warlock": ("Cloth",), "Mage": ("Cloth",), "Priest": ("Cloth",),
    "Rogue": ("Leather",), "Druid": ("Leather",),
    "Hunter": ("Mail",), "Shaman": ("Mail",), "Evoker": ("Mail",),
    "Warrior": ("Plate", "Mail"), "Paladin": ("Plate", "Mail"),
    "Death Knight": ("Plate", "Mail"), "Monk": ("Leather",),
    "Demon Hunter": ("Leather",),
}
# Neck/ring/trinket/caster off-hand all come through as "Miscellaneous".
ARMOR_MISC = ("Miscellaneous",)

# Weapon subclasses (item_class=Weapon) each class may hold.
CLASS_WEAPONS = {
    "Warlock": ("Staff", "Dagger", "One-Handed Sword"),
    "Mage": ("Staff", "Dagger", "One-Handed Sword"),
    "Priest": ("Staff", "Dagger", "One-Handed Sword"),
    "Rogue": ("Dagger", "One-Handed Sword", "One-Handed Axe", "Fist", "Warglaives"),
    "Monk": ("Staff", "", "One-Handed Sword", "One-Handed Axe", "Fist"),
    "Druid": ("Staff", "Dagger", "One-Handed Sword", "One-Handed Mace", "Fist", "Polearm"),
    "Hunter": ("Bow", "Gun", "Crossbow", "Dagger", "One-Handed Sword",
               "One-Handed Axe", "Polearm"),
    "Shaman": ("Staff", "Dagger", "One-Handed Sword", "One-Handed Axe",
               "One-Handed Mace", "Fist"),
    "Evoker": ("Staff", "Dagger", "One-Handed Sword"),
    "Paladin": ("One-Handed Sword", "One-Handed Axe", "One-Handed Mace",
                "Two-Handed Sword", "Two-Handed Axe", "Two-Handed Mace", "Polearm"),
    "Warrior": ("One-Handed Sword", "One-Handed Axe", "One-Handed Mace",
                "Two-Handed Sword", "Two-Handed Axe", "Two-Handed Mace", "Polearm"),
    "Death Knight": ("One-Handed Sword", "Two-Handed Sword",
                     "One-Handed Axe", "Two-Handed Axe", "Polearm"),
    "Demon Hunter": ("Dagger", "One-Handed Sword", "One-Handed Axe", "Fist", "Warglaives"),
}
DEFAULT_WEAPONS = ("Staff", "Dagger", "One-Handed Sword")


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


async def _meta_for(db: AsyncSession, item_id: int) -> dict:
    try:
        return await item_metadata(db, item_id)
    except Exception:
        return {}


def _class_allows(meta: dict, class_name: str) -> bool:
    """Can this character class equip this item? (armor type / weapon subclass)"""
    ic = (meta.get("item_class") or {}).get("name", "")
    isc = (meta.get("item_subclass") or {}).get("name", "")
    if ic == "Armor":
        allowed = CLASS_ARMOR.get(class_name, ())
        return isc in allowed or isc in ARMOR_MISC
    if ic == "Weapon":
        allowed = CLASS_WEAPONS.get(class_name, DEFAULT_WEAPONS)
        return isc in allowed
    return False


async def generate_candidates(
    db: AsyncSession,
    encounter_ids: dict[int, str],       # encounter_id → boss/dungeon name
    worn_items: dict[str, dict],         # canonical slot → {item_id, item_level, ...}
    policy: TrackPolicy,
    max_per_slot: int = 3,
    class_name: str = "",
) -> list[CandidateItem]:
    """One candidate per (item, applicable difficulty), class-filtered.

    Trinkets are simmed against EACH worn trinket (decision 2026-09-03), so
    each trinket item yields two candidates (trinket1 and trinket2). Other
    slots get a single candidate replacing that slot.
    """
    buckets: dict[str, list[CandidateItem]] = {}
    seen: set[tuple[int, int, str]] = set()

    def _add(c: CandidateItem) -> None:
        key = (c.item_id, c.item_level, c.slot)
        if key in seen:
            return
        seen.add(key)
        buckets.setdefault(c.slot, []).append(c)

    for enc_id, enc_name in encounter_ids.items():
        items = await encounter_items(db, enc_id)
        for meta in items:
            item_id, name = meta["item_id"], meta["name"]
            imeta = await _meta_for(db, item_id)
            if not _class_allows(imeta, class_name):
                continue
            inv_type = (imeta.get("inventory_type") or {}).get("name", "")
            slot = _slot_from_inv(inv_type)
            if slot is None:
                continue

            # pairs: trinket items are tried against both worn trinket slots
            family = [slot]
            if slot in ("finger1", "finger2", "trinket1", "trinket2"):
                family = ["trinket1", "trinket2"] if slot.startswith("trinket") \
                    else ["finger1", "finger2"]
            pair_worn = [(worn_items.get(ws, {}).get("item_id"),
                          worn_items.get(ws, {}).get("item_level") or 0)
                         for ws in family]

            def owned(iid: int, ilvl: int) -> bool:
                # same item already worn at equal/higher ilvl — no point simming
                return any(wid == iid and (wil or 0) >= ilvl
                           for wid, wil in pair_worn)

            worn_ilvl = max([wil for _, wil in pair_worn] + [0])
            targets = family if slot.startswith(("finger", "trinket")) else [slot]

            variants = []
            for diff in ("lfr", "normal", "heroic", "mythic"):
                v = policy.raid_variant(item_id, diff)
                if owned(item_id, v["item_level"]):
                    continue
                keep = v["item_level"] >= worn_ilvl or inv_type in ("TRINKET", "FINGER")
                if worn_ilvl and not keep:
                    continue
                v["source"], v["difficulty"], v["variant"] = "raid", diff, None
                variants.append(v)
            for variant in ("great_vault", "bonus_roll"):
                v = policy.mplus_variant(item_id, variant)
                if owned(item_id, v["item_level"]):
                    continue
                if v["item_level"] >= worn_ilvl or inv_type in ("TRINKET", "FINGER"):
                    v["source"], v["difficulty"], v["variant"] = "mplus", "mythic", variant
                    variants.append(v)

            for tgt in targets:
                for v in variants:
                    _add(CandidateItem(
                        item_id=item_id, name=name, slot=tgt,
                        item_level=v["item_level"], bonus_ids=v["bonus_ids"],
                        source=v["source"], difficulty=v["difficulty"],
                        variant=v["variant"], boss_or_dungeon=enc_name,
                        inventory_type=inv_type,
                    ))

    # cap per slot by ilvl desc, keep boss/difficulty variety on ties
    out: list[CandidateItem] = []
    for slot, cands in buckets.items():
        cands.sort(key=lambda c: (-c.item_level, c.boss_or_dungeon, c.source))
        out.extend(cands[:max_per_slot])
    out.sort(key=lambda c: -c.item_level)
    return out


_RAID_ENCOUNTERS: set[int] = set()


def mark_raid_encounters(encounter_ids: list[int]) -> None:
    """Called by content discovery so candidates know the source type."""
    _RAID_ENCOUNTERS.clear()
    _RAID_ENCOUNTERS.update(encounter_ids)


def _is_raid_source(enc_id: int, encounter_ids: dict[int, str]) -> bool:
    return enc_id in _RAID_ENCOUNTERS
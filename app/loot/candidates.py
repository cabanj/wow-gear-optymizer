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
    if key.startswith("off hand") or "off hand" in key or key in ("holdable", "shield"):
        return "off_hand"
    if key and (key.startswith("range") or key.split()[0] in
                ("bow", "gun", "crossbow", "thrown")):
        return "main_hand"  # ranged weapons occupy the main hand slot
    body = key.split()[0] if key else ""
    if body in ("head", "shoulder", "chest", "robe", "wrist", "hands", "waist",
                "legs", "feet", "neck", "back", "cloak"):
        return {"back": "back", "cloak": "back", "robe": "chest"}.get(body, body)
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
# Cloth casters sim staff baseline; 1H options exist so staff can be
# challenged by a 1H + off-hand combo (see combo generation below).
CLASS_WEAPONS = {
    "Warlock": ("Staff", "Dagger", "One-Handed Sword"),
    "Mage": ("Staff", "Dagger", "One-Handed Sword"),
    "Priest": ("Staff", "Dagger", "One-Handed Sword"),
    "Evoker": ("Staff", "Dagger", "One-Handed Sword"),
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
    pset: str = ""       # profileset name (must match builder output)
    # weapon combo (1H + off-hand): second item, main fields describe the 1H
    off_item_id: int = 0
    off_name: str = ""
    off_ilvl: int = 0
    off_bonus_ids: list[int] | None = None
    off_boss: str = ""

    def __post_init__(self):
        if not self.pset:
            self.pset = f"{self.source}_{self.item_id}_{self.slot}"
        if self.off_bonus_ids is None:
            self.off_bonus_ids = []


# Classes that can use a caster-type off-hand (no dual-wield rules involved).
OH_CLASSES = {"Warlock", "Mage", "Priest", "Evoker", "Druid", "Shaman", "Paladin"}
SHIELD_CLASSES = {"Paladin", "Shaman", "Warrior"}

# max 1H+OH combos per character (cartesian 1H x OH, top ilvl sums win)
MAX_COMBOS = 6


async def _meta_for(db: AsyncSession, item_id: int) -> dict:
    try:
        return await item_metadata(db, item_id)
    except Exception:
        return {}


def _class_allows(meta: dict, class_name: str) -> bool:
    """Can this character class equip this item? (armor type / weapon subclass)"""
    ic = (meta.get("item_class") or {}).get("name", "")
    isc = (meta.get("item_subclass") or {}).get("name", "")
    inv = (meta.get("inventory_type") or {}).get("name", "")
    if _is_offhand_inv(inv):
        if isc in ("Shield", "Shields"):
            return class_name in SHIELD_CLASSES
        return class_name in OH_CLASSES
    if ic == "Armor":
        allowed = CLASS_ARMOR.get(class_name, ())
        if not (isc in allowed or isc in ARMOR_MISC):
            return False
        return _primary_ok(meta, class_name) if isc not in ARMOR_MISC else True
    if ic == "Weapon":
        allowed = CLASS_WEAPONS.get(class_name, DEFAULT_WEAPONS)
        if isc not in allowed:
            return False
        return _primary_ok(meta, class_name)
    return False


# Primary stat (STR/AGI/INT) each class actually uses. Checked for Weapon and
# non-Misc Armor — jewelry/trinkets/off-hands-Misc carry stamina + secondaries
# only, so any of those is equippable by everyone. Hybrids allow both of theirs
# (spec-level granularity would need the played spec, not just the class).
CLASS_PRIMARY = {
    "Warlock": ("INTELLECT",), "Mage": ("INTELLECT",), "Priest": ("INTELLECT",),
    "Evoker": ("INTELLECT",),
    "Rogue": ("AGILITY",), "Hunter": ("AGILITY",), "Monk": ("AGILITY",),
    "Demon Hunter": ("AGILITY",),
    "Druid": ("AGILITY", "INTELLECT"), "Shaman": ("AGILITY", "INTELLECT"),
    "Paladin": ("STRENGTH", "INTELLECT"),
    "Warrior": ("STRENGTH",), "Death Knight": ("STRENGTH",),
}
PRIMARY_STATS = ("STRENGTH", "AGILITY", "INTELLECT")


def _primary_stat(meta: dict) -> str | None:
    """Primary stat from the static item preview (presence matters, not value —
    the template is low-ilvl but INT vs AGI/STR never changes with scaling)."""
    stats = ((meta.get("preview_item") or {}).get("stats") or [])
    for s in stats:
        t = ((s.get("type") or {}).get("type") or "")
        if t in PRIMARY_STATS and (s.get("value") or 0) > 0:
            return t
    return None


def _primary_ok(meta: dict, class_name: str) -> bool:
    p = _primary_stat(meta)
    if p is None:
        return True  # no primary on the item (jewelry/trinket) — equippable
    return p in CLASS_PRIMARY.get(class_name, PRIMARY_STATS)


def _is_offhand_inv(inv: str) -> bool:
    key = (inv or "").replace("_", " ").replace("-", " ").strip().lower()
    key = " ".join(key.split())
    return key.startswith("off hand") or key in ("holdable", "held in off hand")


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
    onehanders: dict[int, dict] = {}  # item_id -> {name, boss} for 1H weapons
    offhands: dict[int, dict] = {}    # item_id -> {name, boss} for off-hands

    def _add(c: CandidateItem) -> None:
        key = (c.item_id, c.item_level, c.slot)
        if key in seen:
            return
        seen.add(key)
        buckets.setdefault(c.slot, []).append(c)

    def _is_onehand(imeta: dict) -> bool:
        if (imeta.get("item_class") or {}).get("name") != "Weapon":
            return False
        inv = (imeta.get("inventory_type") or {}).get("name", "")
        key = " ".join(inv.replace("_", " ").replace("-", " ").split()).lower()
        return key.startswith(("one hand", "main hand"))

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

            # pool 1H weapons + off-hands for combo generation (no lone 1H
            # candidates: a 1H without off-hand is never a real setup)
            if _is_onehand(imeta):
                onehanders[item_id] = {"name": name, "boss": enc_name, "enc_id": enc_id}
                if not worn_items.get("off_hand", {}).get("item_id"):
                    continue  # combos only; lone 1H needs a worn off-hand
            elif _is_offhand_inv(inv_type):
                offhands[item_id] = {"name": name, "boss": enc_name, "enc_id": enc_id}
                continue  # off-hands only ever sim as part of a combo

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
                v = policy.raid_variant(item_id, diff, enc_id)
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

    # 1H + off-hand combos (staff challengers): same-tier pairs only,
    # top ilvl sums win, capped — a cartesian of everything would explode sims
    worn_mh = worn_items.get("main_hand", {})
    worn_oh = worn_items.get("off_hand", {})
    if onehanders and offhands:
        combos = []
        for mh_id, mh in onehanders.items():
            for oh_id, oh in offhands.items():
                for _tier, diff, variant in (
                        ("raid", "mythic", None),
                        ("vault", "mythic", "great_vault")):
                    mhv = policy.raid_variant(mh_id, "mythic", mh.get("enc_id")) if _tier == "raid" \
                        else policy.mplus_variant(mh_id, "great_vault")
                    ohv = policy.raid_variant(oh_id, "mythic", oh.get("enc_id")) if _tier == "raid" \
                        else policy.mplus_variant(oh_id, "great_vault")
                    if (worn_mh.get("item_id") == mh_id and (worn_mh.get("item_level") or 0) >= mhv["item_level"]
                            and worn_oh.get("item_id") == oh_id and (worn_oh.get("item_level") or 0) >= ohv["item_level"]):
                        continue  # exact combo already worn
                    combos.append((mhv["item_level"] + ohv["item_level"], mh_id, mh, mhv,
                                   oh_id, oh, ohv, _tier, diff, variant))
        combos.sort(key=lambda t: -t[0])
        combo_items = []
        for _, mh_id, mh, mhv, oh_id, oh, ohv, tier, diff, variant in combos[:MAX_COMBOS]:
            src = "raid" if tier == "raid" else "mplus"
            combo_items.append(CandidateItem(
                item_id=mh_id, name=f"{mh['name']} + {oh['name']}",
                slot="main_hand",
                item_level=max(mhv["item_level"], ohv["item_level"]),
                bonus_ids=mhv["bonus_ids"], source=src, difficulty=diff,
                variant=variant,
                boss_or_dungeon=f"{mh['boss']} / {oh['boss']}",
                inventory_type="Two-Hand",
                pset=f"{src}_combo_{mh_id}x{oh_id}_main_hand",
                off_item_id=oh_id, off_name=oh["name"],
                off_ilvl=ohv["item_level"], off_bonus_ids=ohv["bonus_ids"],
                off_boss=oh["boss"],
            ))
        for c in combo_items:
            _add(c)

    # cap per slot by ilvl desc, keep boss/difficulty variety on ties —
    # combos bypass the cap (already capped globally at MAX_COMBOS).
    # Everything at the slot's top ilvl is kept (same-ilvl variety must not
    # lose to an alphabetical tiebreak); the cap applies to lower tiers only.
    combo_keys = {(c.item_id, c.item_level, c.slot) for c in combo_items} \
        if onehanders and offhands else set()
    out: list[CandidateItem] = []
    for slot, cands in buckets.items():
        cands.sort(key=lambda c: (-c.item_level, c.boss_or_dungeon, c.source))
        fixed = [c for c in cands if (c.item_id, c.item_level, c.slot) in combo_keys]
        rest = [c for c in cands if (c.item_id, c.item_level, c.slot) not in combo_keys]
        top_ilvl = max([c.item_level for c in rest] or [0])
        top = [c for c in rest if c.item_level == top_ilvl]
        lower = [c for c in rest if c.item_level < top_ilvl][:max_per_slot]
        out.extend(fixed + top + lower)
    out.sort(key=lambda c: -c.item_level)
    return out


_RAID_ENCOUNTERS: set[int] = set()


def mark_raid_encounters(encounter_ids: list[int]) -> None:
    """Called by content discovery so candidates know the source type."""
    _RAID_ENCOUNTERS.clear()
    _RAID_ENCOUNTERS.update(encounter_ids)


def _is_raid_source(enc_id: int, encounter_ids: dict[int, str]) -> bool:
    return enc_id in _RAID_ENCOUNTERS
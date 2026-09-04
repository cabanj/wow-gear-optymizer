"""Tests for class-aware candidate generation and slot mapping."""
import sys

sys.path.insert(0, ".")

import pytest

from app.loot.candidates import _slot_from_inv, _class_allows, generate_candidates


def test_slot_from_inv():
    assert _slot_from_inv("Two-Hand") == "main_hand"
    assert _slot_from_inv("Two-Handed") == "main_hand"
    assert _slot_from_inv("One-Hand") == "main_hand"
    assert _slot_from_inv("Main Hand") == "main_hand"
    assert _slot_from_inv("Off Hand") == "off_hand"
    assert _slot_from_inv("Holdable") == "off_hand"
    assert _slot_from_inv("Trinket") == "trinket1"
    assert _slot_from_inv("Finger") == "finger1"
    assert _slot_from_inv("") is None
    assert _slot_from_inv("Ranged Rifle") == "main_hand"


def test_class_allows_armor_weapon_offhand():
    cloth = {"item_class": {"name": "Armor"}, "item_subclass": {"name": "Cloth"}}
    leather = {"item_class": {"name": "Armor"}, "item_subclass": {"name": "Leather"}}
    trink = {"item_class": {"name": "Armor"}, "item_subclass": {"name": "Miscellaneous"}}
    staff = {"item_class": {"name": "Weapon"}, "item_subclass": {"name": "Staff"}}
    axe = {"item_class": {"name": "Weapon"}, "item_subclass": {"name": "Two-Handed Axe"}}
    dagger = {"item_class": {"name": "Weapon"}, "item_subclass": {"name": "Dagger"},
              "inventory_type": {"name": "One-Hand"}}
    lamp = {"item_class": {"name": "Armor"}, "item_subclass": {"name": "Miscellaneous"},
            "inventory_type": {"name": "Held In Off-hand"}}
    shield = {"item_class": {"name": "Armor"}, "item_subclass": {"name": "Shields"},
              "inventory_type": {"name": "Off Hand"}}
    assert _class_allows(cloth, "Warlock")
    assert not _class_allows(leather, "Warlock")
    assert _class_allows(trink, "Warlock")
    assert _class_allows(staff, "Warlock")
    assert not _class_allows(axe, "Warlock")
    assert _class_allows(axe, "Warrior")
    assert not _class_allows(staff, "Rogue")
    assert _class_allows(dagger, "Warlock")
    assert _class_allows(lamp, "Warlock")
    assert not _class_allows(shield, "Warlock")
    assert _class_allows(shield, "Paladin")


# --- integration: candidate generation via monkeypatched discovery ---
class FakeDB:
    def __init__(self, items):
        self.items = items  # id -> {class, subclass, inv, boss}

    async def item_metadata(self, item_id):
        d = self.items[item_id]
        return {"item_class": {"name": d["class"]},
                "item_subclass": {"name": d["subclass"]},
                "inventory_type": {"name": d["inv"]}}


class FakePolicy:
    def raid_variant(self, item_id, diff, encounter_id=None):
        return {"item_id": item_id, "source": "raid", "difficulty": diff,
                "item_level": {"lfr": 280, "normal": 292, "heroic": 305,
                               "mythic": 334}[diff],
                "bonus_ids": [6652], "variant": None}

    def mplus_variant(self, item_id, variant):
        return {"item_id": item_id, "source": "mplus", "difficulty": "mythic",
                "item_level": 318, "bonus_ids": [6652], "variant": variant}


ITEMS = {
    101: {"class": "Armor", "subclass": "Cloth", "inv": "Head"},
    102: {"class": "Armor", "subclass": "Leather", "inv": "Chest"},
    103: {"class": "Armor", "subclass": "Miscellaneous", "inv": "Trinket"},
    104: {"class": "Weapon", "subclass": "Staff", "inv": "Two-Hand"},
    105: {"class": "Weapon", "subclass": "Two-Handed Axe", "inv": "Two-Hand"},
    106: {"class": "Armor", "subclass": "Cloth", "inv": "Shoulder"},
    107: {"class": "Armor", "subclass": "Miscellaneous", "inv": "Trinket"},
}
WORN = {"head": {"item_id": 900, "item_level": 300},
        "main_hand": {"item_id": 901, "item_level": 331},
        "trinket1": {"item_id": 902, "item_level": 310},
        "trinket2": {"item_id": 903, "item_level": 300}}


def test_generate_class_filtered_no_dupes(monkeypatch):
    import asyncio
    from app.loot import candidates as C

    async def fake_encounter(adb, enc_id):
        out = []
        for iid in ITEMS:
            d = ITEMS[iid]
            if d["inv"] in ("Head", "Chest", "Shoulder", "Two-Hand", "Trinket"):
                out.append({"item_id": iid, "name": f"item{iid}"})
        return out

    async def fake_meta(adb, item_id):
        d = ITEMS[item_id]
        return {"item_class": {"name": d["class"]},
                "item_subclass": {"name": d["subclass"]},
                "inventory_type": {"name": d["inv"]}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    async def run():
        return await generate_candidates(None, {1: "Boss"}, WORN, FakePolicy(),
                                         max_per_slot=3, class_name="Warlock")

    cands = asyncio.run(run())
    # all are Warlock-equippable: no axe(105), no leather(102)
    ids = [c.item_id for c in cands]
    assert 105 not in ids
    assert 102 not in ids
    # staff 2H present as main_hand candidate
    assert any(c.item_id == 104 and c.slot == "main_hand" for c in cands)
    # no duplicates: same (item, ilvl, slot) appears once
    keyed = [(c.item_id, c.item_level, c.slot) for c in cands]
    assert len(keyed) == len(set(keyed))
    # trinkets tried against both slots (each trinket item yields 2 targets)
    tk1 = [c.slot for c in cands if c.item_id == 103]
    assert set(tk1) == {"trinket1", "trinket2"}


def _meta_with_stats(cls, sub, inv, primary=None):
    stats = []
    if primary:
        stats.append({"type": {"type": primary}, "value": 100})
    stats.append({"type": {"type": "STAMINA"}, "value": 500})
    return {"item_class": {"name": cls}, "item_subclass": {"name": sub},
            "inventory_type": {"name": inv},
            "preview_item": {"stats": stats}}


def test_class_allows_primary_stat():
    agi_dagger = _meta_with_stats("Weapon", "Dagger", "One-Hand", "AGILITY")
    int_dagger = _meta_with_stats("Weapon", "Dagger", "One-Hand", "INTELLECT")
    int_staff = _meta_with_stats("Weapon", "Staff", "Two-Hand", "INTELLECT")
    ring = _meta_with_stats("Armor", "Miscellaneous", "Finger")  # no primary
    int_cloth = _meta_with_stats("Armor", "Cloth", "Head", "INTELLECT")
    str_cloth = _meta_with_stats("Armor", "Cloth", "Head", "STRENGTH")
    assert not _class_allows(agi_dagger, "Warlock")
    assert _class_allows(int_dagger, "Warlock")
    assert _class_allows(int_staff, "Warlock")
    assert _class_allows(ring, "Warlock")  # jewelry has no primary — keep
    assert _class_allows(int_cloth, "Warlock")
    assert not _class_allows(str_cloth, "Warlock")
    assert _class_allows(agi_dagger, "Rogue")
    assert _class_allows(agi_dagger, "Druid")  # hybrid allows both
    assert _class_allows(int_dagger, "Druid")
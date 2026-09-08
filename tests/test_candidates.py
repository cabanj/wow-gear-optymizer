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


def test_quarantined_item_skipped_and_reported(monkeypatch):
    import asyncio
    from app.loot import candidates as C
    from app.loot.candidates import generate_candidates, quarantine_reason

    assert quarantine_reason(270162)
    assert quarantine_reason(270163) is None

    async def fake_encounter(adb, enc_id):
        return [{"item_id": 270162, "name": "Soulcoiler Ritual Vessel"},
                {"item_id": 270163, "name": "Sszorak's Ferocity"}]

    async def fake_meta(adb, item_id):
        return {"item_class": {"name": "Armor"},
                "item_subclass": {"name": "Miscellaneous"},
                "inventory_type": {"name": "Trinket"}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    async def run():
        skipped = []
        cands = await generate_candidates(
            None, {1: "Boss"},
            {"trinket1": {"item_id": 900, "item_level": 300},
             "trinket2": {"item_id": 901, "item_level": 300}},
            FakePolicy(), max_per_slot=3, class_name="Warlock",
            skipped=skipped)
        return cands, skipped

    cands, skipped = asyncio.run(run())
    ids = [c.item_id for c in cands]
    assert 270162 not in ids
    assert 270163 in ids
    assert len(skipped) == 1 and skipped[0]["item_id"] == 270162


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

def test_one_variant_per_item_max_ilvl(monkeypatch):
    """Same item at several difficulties → single candidate at max ilvl."""
    import asyncio
    from app.loot import candidates as C
    from app.loot.candidates import generate_candidates

    async def fake_encounter(adb, enc_id):
        return [{"item_id": 101, "name": "item101"},
                {"item_id": 103, "name": "item103"}]

    async def fake_meta(adb, item_id):
        inv = "Head" if item_id == 101 else "Trinket"
        return {"item_class": {"name": "Armor"},
                "item_subclass": {"name": "Cloth" if item_id == 101 else "Miscellaneous"},
                "inventory_type": {"name": inv}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    async def run():
        return await generate_candidates(
            None, {1: "Boss"},
            {"head": {"item_id": 900, "item_level": 300},
             "trinket1": {"item_id": 902, "item_level": 300},
             "trinket2": {"item_id": 903, "item_level": 300}},
            FakePolicy(), max_per_slot=3, class_name="Warlock")

    cands = asyncio.run(run())
    heads = [c for c in cands if c.item_id == 101]
    assert len(heads) == 1  # not 4 difficulties + vault
    assert heads[0].item_level == 334  # mythic max (FakePolicy)
    assert heads[0].source == "raid"


def test_catalyst_tier_candidates_at_mythic(monkeypatch):
    """Tier pieces from the snapshot become mythic Catalyst candidates."""
    import asyncio
    from app.loot import candidates as C
    from app.loot.candidates import generate_candidates, tier_piece_map

    async def fake_encounter(adb, enc_id):
        return []

    async def fake_meta(adb, item_id):
        return {"item_class": {"name": "Armor"},
                "item_subclass": {"name": "Cloth"},
                "inventory_type": {"name": "Head"}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    raw = {"equipment": {"equipped_item_sets": [
        {"item_set": {"name": "Shattered Restraints"},
         "display_string": "Shattered Restraints (4/5)",
         "effects": [],
         "items": [{"item": {"id": 271546, "name": "Skull of the Damned Necrolyte"}}]}]}}
    worn = {"head": {"item_id": 271546, "item_level": 300}}

    async def run():
        tier_map = await tier_piece_map(None, raw, worn)
        assert tier_map == {"head": {"item_id": 271546,
                                     "name": "Skull of the Damned Necrolyte"}}
        cands = await generate_candidates(
            None, {1: "Boss"}, worn, FakePolicy(),
            max_per_slot=3, class_name="Warlock", tier_pieces=tier_map)
        return cands

    cands = asyncio.run(run())
    heads = [c for c in cands if c.item_id == 271546]
    assert len(heads) == 1
    assert heads[0].item_level == 334
    assert heads[0].variant == "catalyst"
    assert heads[0].boss_or_dungeon == "Catalyst"


def test_catalyst_owned_at_mythic_skipped(monkeypatch):
    import asyncio
    from app.loot import candidates as C
    from app.loot.candidates import generate_candidates

    async def fake_encounter(adb, enc_id):
        return []

    async def fake_meta(adb, item_id):
        return {"item_class": {"name": "Armor"},
                "item_subclass": {"name": "Cloth"},
                "inventory_type": {"name": "Head"}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    async def run():
        return await generate_candidates(
            None, {1: "Boss"},
            {"head": {"item_id": 271546, "item_level": 334}},
            FakePolicy(), max_per_slot=3, class_name="Warlock",
            tier_pieces={"head": {"item_id": 271546, "name": "Skull"}})

    assert asyncio.run(run()) == []


def test_dungeon_trinkets_vault_only_class_filtered(monkeypatch):
    """Dungeon pool: trinkets in at vault ilvl, other slots ignored."""
    import asyncio
    from app.loot import candidates as C
    from app.loot.candidates import generate_candidates

    async def fake_encounter(adb, enc_id):
        if enc_id == 9:
            return [{"item_id": 301, "name": "dungeon trinket"},
                    {"item_id": 302, "name": "dungeon chest"}]
        return []

    async def fake_meta(adb, item_id):
        if item_id == 301:
            return {"item_class": {"name": "Armor"},
                    "item_subclass": {"name": "Miscellaneous"},
                    "inventory_type": {"name": "Trinket"}}
        return {"item_class": {"name": "Armor"},
                "item_subclass": {"name": "Cloth"},
                "inventory_type": {"name": "Chest"}}

    monkeypatch.setattr(C, "encounter_items", fake_encounter)
    monkeypatch.setattr(C, "item_metadata", fake_meta)

    async def run():
        return await generate_candidates(
            None, {},  # no raid encounters
            {"trinket1": {"item_id": 900, "item_level": 300},
             "trinket2": {"item_id": 901, "item_level": 300}},
            FakePolicy(), max_per_slot=3, class_name="Warlock",
            dungeon_encounters={9: "Den of Nalorakk · Nalorakk"})

    cands = asyncio.run(run())
    by_id = {}
    for c in cands:
        by_id.setdefault(c.item_id, []).append(c)
    assert 302 not in by_id  # chest ignored in dungeon pool
    assert set(c.slot for c in by_id[301]) == {"trinket1", "trinket2"}
    assert all(c.item_level == 318 and c.source == "mplus" for c in by_id[301])
    assert all(c.boss_or_dungeon == "Den of Nalorakk · Nalorakk" for c in by_id[301])

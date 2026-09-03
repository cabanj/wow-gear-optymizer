"""Tests for candidate generation."""
import pytest

from app.loot.candidates import INV_TO_SLOT, CandidateItem
from app.loot.upgrade_rules import TrackPolicy


SEED = {
    "raid": {
        "lfr": {"ilvl": 289, "bonus_ids": [12824]},
        "normal": {"ilvl": 302, "bonus_ids": [12832]},
        "heroic": {"ilvl": 315, "bonus_ids": [12844]},
        "mythic": {"ilvl": 334, "bonus_ids": [12854]},
    },
    "mplus": {
        "great_vault": {"ilvl": 318, "bonus_ids": [12845]},
        "bonus_roll": {"ilvl": 318, "bonus_ids": [12845]},
    },
}


def test_track_policy_load(tmp_path):
    p = tmp_path / "seed.json"
    p.write_text(__import__("json").dumps(SEED))
    pol = TrackPolicy.load(str(p))
    v = pol.raid_variant(999, "mythic")
    assert v["item_level"] == 334
    assert v["bonus_ids"] == [6652, 12854]
    m = pol.mplus_variant(999, "great_vault")
    assert m["item_level"] == 318
    assert m["variant"] == "great_vault"


def test_inv_to_slot_mapping():
    assert INV_TO_SLOT["TRINKET"] == "trinket1"
    assert INV_TO_SLOT["FINGER"] == "finger1"
    assert INV_TO_SLOT["TWO_HANDED"] == "main_hand"
    assert INV_TO_SLOT["HOLDABLE"] == "off_hand"

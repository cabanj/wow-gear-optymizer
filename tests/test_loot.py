"""Tests for loot discovery logic (mocked Blizzard responses)."""
import pytest

from app.loot.discovery import _is_raid
from app.loot.upgrade_rules import ItemVariant, filter_compatible, mplus_variants, raid_variants


def test_is_raid_true_for_raid_modes():
    # Venomous Abyss (current S2 raid) shape: LFR/N/H/M tracked, no keystone mode
    inst = {"modes": [
        {"mode": {"type": "LFR"}, "is_tracked": True},
        {"mode": {"type": "NORMAL"}, "is_tracked": True},
        {"mode": {"type": "HEROIC"}, "is_tracked": True},
        {"mode": {"type": "MYTHIC"}, "is_tracked": True},
    ]}
    assert _is_raid(inst) is True


def test_is_raid_false_for_mplus_dungeon():
    # M+ dungeons carry an untracked MYTHIC_KEYSTONE mode (verified live)
    inst = {"modes": [
        {"mode": {"type": "NORMAL"}, "is_tracked": True},
        {"mode": {"type": "HEROIC"}, "is_tracked": True},
        {"mode": {"type": "MYTHIC"}, "is_tracked": True},
        {"mode": {"type": "MYTHIC_KEYSTONE"}, "is_tracked": False},
    ]}
    assert _is_raid(inst) is False


def test_is_raid_false_for_keystone_pseudo_instance():
    inst = {"modes": [
        {"mode": {"type": "NORMAL"}, "is_tracked": False},
        {"mode": {"type": "MYTHIC"}, "is_tracked": False},
        {"mode": {"type": "MYTHIC_KEYSTONE"}, "is_tracked": False},
    ]}
    assert _is_raid(inst) is False


def test_raid_variants_one_per_difficulty():
    ladder = {
        "lfr": (710, [1000]),
        "normal": (723, [1001]),
        "heroic": (736, [1002]),
        "mythic": (749, [1003]),
    }
    out = raid_variants(250462, ladder)
    assert len(out) == 4
    assert out[3]["item_level"] == 749
    assert out[3]["bonus_ids"] == [1003]


def test_mplus_variants_vault_and_bonus_roll_only():
    out = mplus_variants(999, 739, 729, [700])
    assert len(out) == 2
    assert [v["variant"] for v in out] == ["great_vault", "bonus_roll"]
    assert out[0]["bonus_ids"] == [700, 0]  # VAULT_BONUS_ID placeholder resolved at seed


def test_filter_compatible_skips_same_unique_item():
    worn = {"trinket1": {"item_id": 250462}}
    cands = [
        {"item_id": 250462, "variant": None},
        {"item_id": 999, "variant": None},
    ]
    out = filter_compatible("trinket1", worn, cands)
    assert [c["item_id"] for c in out] == [999]

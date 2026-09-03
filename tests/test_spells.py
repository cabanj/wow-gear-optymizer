"""Tests for spell description scaling."""
import sys

sys.path.insert(0, ".")

from app.simc.spells import scale_description


def test_scale_value_and_duration():
    d = "Equip: Your abilities have a chance to grant you 33 Critical Strike for 12 sec."
    out = scale_description(d, 456.38, "12 seconds", "Crit")
    assert out == "Equip: Your abilities have a chance to grant you 456 Critical Strike for 12 sec."


def test_scale_leaves_cooldown_alone():
    d = "Use: Echo the drum. (4 Sec Cooldown)"
    out = scale_description(d, None, None, None)
    assert out == d


def test_no_value_keeps_base():
    d = "Equip: grant you 33 Critical Strike for 12 sec."
    assert scale_description(d, None, None, None) == d

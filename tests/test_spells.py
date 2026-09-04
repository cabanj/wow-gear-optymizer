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


def test_scale_random_secondary_stat():
    d = "Use: Take a small sip of venom, gaining 513 of a random secondary stat for 15 sec."
    out = scale_description(d, 913.93, None, None)
    assert out == "Use: Take a small sip of venom, gaining 914 of a random secondary stat for 15 sec."


def test_scale_does_not_touch_cooldown_number():
    d = "Use: Echo the drum. (4 Sec Cooldown)"
    out = scale_description(d, 0.0, None, None)
    assert out == d


def test_scale_effigy_secondary_and_tertiary():
    d = ("Equip: Your spells and abilities have a chance to grant you 178 "
         "of a random secondary stat and 89 of a random tertiary stat for 12 sec.")
    out = scale_description(d, 362.17, None, None, 181.10)
    assert out == ("Equip: Your spells and abilities have a chance to grant you 362 "
                   "of a random secondary stat and 181 of a random tertiary stat for 12 sec.")


def test_scale_gain_and_reduction():
    d = ("Use: Take a small sip of venom, gaining 513 of a random secondary stat "
         "for 15 sec. Afterwards, a random secondary stat is reduced by 73 "
         "for 15 sec. (2 Min Cooldown)")
    out = scale_description(d, 913.93, None, None, 130.58)
    assert out == ("Use: Take a small sip of venom, gaining 914 of a random secondary stat "
                   "for 15 sec. Afterwards, a random secondary stat is reduced by 131 "
                   "for 15 sec. (2 Min Cooldown)")

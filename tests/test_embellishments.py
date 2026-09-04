"""Tests for embellishment detection from Armory bonus_list."""
import sys

sys.path.insert(0, ".")

from app.loot.embellishments import embellishments_for, load_embellishments


def test_seed_loads():
    emb = load_embellishments()
    assert len(emb) >= 50
    assert emb[12384]["name"] == "Arcanoweave Lining"


def test_wrist_and_staff_detected():
    wrist = embellishments_for([12214, 12497, 13751, 14001, 8960, 12384, 8791, 13696])
    assert [e["name"] for e in wrist] == ["Arcanoweave Lining"]
    staff = embellishments_for([12214, 12497, 13751, 14001, 13771, 8960, 8790])
    assert [e["name"] for e in staff] == ["Hunter's Ritual Stone"]


def test_no_embellishment():
    assert embellishments_for([6652, 12843, 13690]) == []
    assert embellishments_for([]) == []
    assert embellishments_for(None) == []

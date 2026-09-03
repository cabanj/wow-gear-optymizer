"""Tests for /simc addon import parser."""
from app.simc.importer import parse_simc_addon


SAMPLE = """# SimC Addon 11.x
spec=frost
level=90
race=pandaren
head=icy_veil_circlet,id=268100,bonus_id=6652/12842,ilevel=308,enchant=enchant_head_1
trinket1=vile_vial,id=273796,bonus_id=6652/12699/12843,gems=16vers_7haste
finger1=band,id=251148,bonus_id=6652/12849,enchant=enchant_ring_1
"""


def test_parse_valid():
    parsed = parse_simc_addon(SAMPLE)
    assert parsed is not None
    assert parsed["spec"] == "frost"
    assert parsed["gear"]["head"]["item_id"] == 268100
    assert parsed["gear"]["head"]["bonus_ids"] == [6652, 12842]
    assert parsed["gear"]["trinket1"]["gem_ids"] == ["16vers_7haste"]
    assert parsed["gear"]["finger1"]["enchant"] == "enchant_ring_1"
    assert parsed["item_level"] == 308.0


def test_parse_invalid_returns_none():
    assert parse_simc_addon("") is None
    assert parse_simc_addon("random text without spec") is None
    assert parse_simc_addon("spec=frost\nno gear lines here") is None

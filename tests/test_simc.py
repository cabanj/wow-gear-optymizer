"""Tests for simc profile builder and json2 parser."""
import json

import pytest

from app.simc.profile_builder import Candidate, build_profileset_input
from app.simc.parser import ProfileResult, compute_ranking, extract_results, parse_json2


SNAPSHOT = {
    "summary": {"name": "Testchar", "realm": {"slug": "ravencrest"}},
    "equipment": {"character": {"name": "Testchar"}, "equipped_items": [
        {"slot": {"type": "TRINKET_1"}, "item": {"id": 100, "name": "Worn Trinket", "level": {"value": 700}}}
    ]},
}

CANDS = [
    Candidate(item_id=200001, name="Raid Trinket", slot="trinket1", item_level=729,
              bonus_ids=[10353, 10890], source="raid", boss_or_dungeon="Boss 6"),
    Candidate(item_id=300001, name="M+ Ring", slot="finger1", item_level=723,
              bonus_ids=[10507], source="mplus", boss_or_dungeon="Dungeon X"),
]


def test_profileset_contains_baseline_and_candidates():
    text = build_profileset_input(
        SNAPSHOT, CANDS, "raid",
        {"iterations": 10000, "target_error": 0.002, "fight_style": "Patchwerk",
         "duration": 300, "threads": 8, "profileset_work_threads": 2},
    )
    assert "armory=eu,ravencrest,testchar" in text
    assert 'profileset."raid_200001_trinket1"' in text
    assert "trinket1=raid_trinket,id=200001" in text
    assert "bonus_id=10353/10890" in text
    assert "ilevel=729" in text
    assert "fight_style=Patchwerk" in text
    assert "iterations=10000" in text
    assert "profileset_metric=dps" in text


def test_trinket_candidate_gets_replace_variant():
    from app.simc.profile_builder import Candidate as C
    trink = C(item_id=200001, name="T", slot="trinket1", item_level=729,
              bonus_ids=[1], source="raid", replace_slot="trinket2")
    text = build_profileset_input(
        SNAPSHOT, [trink], "raid",
        {"iterations": 100, "target_error": 0.01, "fight_style": "Patchwerk",
         "duration": 300},
    )
    assert "replaces_trinket2" in text


def test_item_line_slot_prefix_and_combo():
    from app.simc.profile_builder import _item_line, _item_lines, _slug, Candidate as C
    assert _slug("Aln'hara Cane") == "aln'hara_cane"
    assert _slug("Caustic Chain-Wrapped Sash") == "caustic_chain-wrapped_sash"
    assert _slug("Jan'thrazet, the Soul Fang") == "jan'thrazet_the_soul_fang"
    single = C(item_id=1, name="Shawl", slot="shoulder", item_level=334,
               bonus_ids=[6652, 12854], source="raid")
    assert _item_line(single) == "shoulders=shawl,id=1,bonus_id=6652/12854,ilevel=334"
    assert _item_lines(single, "n") == [
        'profileset."n"=shoulders=shawl,id=1,bonus_id=6652/12854,ilevel=334']
    wrist = C(item_id=2, name="W", slot="wrist", item_level=334,
              bonus_ids=[6652], source="raid")
    assert _item_line(wrist).startswith("wrists=w,")
    repl = C(item_id=3, name="T", slot="trinket1", item_level=334,
             bonus_ids=[6652], source="raid", replace_slot="trinket2")
    assert _item_line(repl).startswith("trinket2=t,")
    combo = C(item_id=4, name="Hexing Spiritrender", slot="main_hand",
              item_level=334, bonus_ids=[6652], source="raid", pset="c",
              off_item_id=5, off_name="Spine of the Hissing Abyss",
              off_bonus_ids=[6652], off_ilevel=334)
    assert _item_lines(combo, "c") == [
        'profileset."c"=main_hand=hexing_spiritrender,id=4,bonus_id=6652,ilevel=334',
        'profileset."c"+=off_hand=spine_of_the_hissing_abyss,id=5,bonus_id=6652,ilevel=334']


def test_json2_parsing_and_ranking():
    payload = {"sim": {"players": [
        {"name": "Baseline", "collected_data": {"iterations": 10000, "dps": {
            "mean": 1_000_000, "median": 999_000, "min": 900_000, "max": 1_100_000,
            "std_dev": 15_000}}},
        {"name": "raid_200001_trinket1", "collected_data": {"iterations": 10000, "dps": {
            "mean": 1_050_000, "median": 1_049_000, "min": 950_000, "max": 1_150_000,
            "std_dev": 15_000}}},
        {"name": "raid_200002_chest", "collected_data": {"iterations": 10000, "dps": {
            "mean": 1_005_000, "median": 1_004_000, "min": 905_000, "max": 1_105_000,
            "std_dev": 15_000}}},
    ]}}
    results = extract_results(parse_json2(json.dumps(payload)))
    assert len(results) == 3
    ranking = compute_ranking(results)
    assert ranking[0]["rank"] == 1
    assert ranking[0]["name"] == "raid_200001_trinket1"
    assert ranking[0]["delta_dps"] == pytest.approx(50_000)
    assert ranking[0]["delta_percent"] == pytest.approx(5.0, rel=1e-3)
    assert ranking[0]["within_error"] is False
    assert ranking[1]["delta_dps"] == pytest.approx(5_000)
    assert ranking[1]["within_error"] is True  # 5k < 2*15k


def test_ranking_without_baseline_raises():
    results = [ProfileResult("x", 1, 1, 1, 1, 1, 1, None)]
    with pytest.raises(ValueError):
        compute_ranking(results)

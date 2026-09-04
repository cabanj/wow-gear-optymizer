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


def test_profileset_line_ends_with_profileset_keyword():
    from app.simc.profile_builder import build_profileset_input, Candidate as C
    SNAPSHOT = {
        "summary": {"name": "Testchar", "realm": {"slug": "ravencrest"}},
        "equipment": {"character": {"name": "Testchar"}, "equipped_items": [
            {"slot": {"type": "TRINKET_1"}, "item": {"id": 100, "name": "Worn Trinket", "level": {"value": 700}}}
        ]},
    }
    text = build_profileset_input(
        SNAPSHOT, [
            C(item_id=200001, name="Raid Trinket 1", slot="trinket1",
                      item_level=729, bonus_ids=[10353, 10890],
                      source="raid", boss_or_dungeon="Boss 6"),
        ], "raid",
        {"iterations": 10000, "target_error": 0.002, "fight_style": "Patchwerk",
         "duration": 300, "threads": 8, "profileset_work_threads": 2},
    )
    assert 'profileset."raid_200001_trinket1"' in text
    assert "trinket1=raid_trinket_1,id=200001" in text

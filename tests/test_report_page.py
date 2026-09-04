"""Tests for the Jinja report/characters pages (structure, filters, links)."""
import sys

sys.path.insert(0, ".")

from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("app/templates"))


def _row(**kw):
    d = {"rank": 1, "name": "raid_1", "item_name": "Shellbound Bracers", "item_id": 1,
         "slot": "wrist", "slot_label": "Wrist", "source": "raid",
         "source_label": "Raid mythic", "boss": "The Lost Explorers",
         "ilvl": 334, "bonus_ids": "6652/12854", "replaces": "Old Bracers",
         "replaces_item_id": 2, "replaces_ilvl": 300, "quality": "epic", "stats": "",
         "dps_fmt": "37 374", "median_fmt": "37 370", "delta_fmt": "48",
         "pct_fmt": "0.13", "err_pct": "2.89", "std_fmt": "1 078",
         "iterations": 10000, "within_error": True, "bar_pct": 100}
    d.update(kw)
    return d


def _ctx():
    rows = [_row(), _row(rank=2, name="mplus_2", item_name="Crown",
                         source="mplus", slot="head", slot_label="Head",
                         within_error=False, bar_pct=50)]
    return {"user": {"battletag": "T#1"},
            "character": {"name": "Calipse", "realm": "shadowsong",
                          "spec": "Demonology", "item_level": 317},
            "snapshot_time": "2026-09-03 22:17 UTC",
            "snapshot_source": "Blizzard Armory",
            "simulated_at": "2026-09-04 10:05 UTC",
            "simc_version": "1210-01", "wow_build": "12.1.0.69587",
            "content_version": "raid:1320;season:18",
            "baseline_fmt": "37 326",
            "best": {"pct": "0.13", "dps": "48", "name": "Shellbound Bracers",
                     "boss": "The Lost Explorers", "ilvl": 334},
            "top3": rows[:2], "rows": rows,
            "slots": [("head", "Head"), ("wrist", "Wrist")],
            "warning": None}


def test_report_renders_top3_and_slots():
    html = env.get_template("report_detail.html").render(**_ctx())
    assert "Top 3 upgrades" in html
    assert "Browse by slot" in html
    assert 'data-s="head"' in html  # canonical slot value matches data-slot
    assert 'data-slot="head"' in html
    assert "Baseline DPS over time" not in html
    assert "hist" not in html


def test_report_replaces_link():
    html = env.get_template("report_detail.html").render(**_ctx())
    assert "https://www.wowhead.com/item=2" in html
    assert "Item Level 300" in html


def test_characters_latest_report_link():
    c = {"id": "1", "name": "Calipse", "realm_slug": "shadowsong",
         "class_name": "Warlock", "class_color": "#9482C9",
         "active_spec_name": "Demonology", "selected": True,
         "snapshot_time": "2026-09-03 22:17"}
    html = env.get_template("characters.html").render(
        user={"battletag": "T#1"}, characters=[c], current=c,
        gear_left=[], gear_right=[], sections=[], armor_rows=[], weapon_rows=[],
        latest_report={"id": "abc", "finished_at": "2026-09-04 10:05",
                       "profile_type": "raid"})
    assert "/reports/abc" in html
    assert "Showing gear" not in html

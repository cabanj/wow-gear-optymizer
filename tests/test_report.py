"""Tests for HTML report generation."""
import json
import os

from app.reports.html_report import render_report


DATA = {
    "ranking": [
        {"rank": 1, "name": "raid_268230_head", "dps": 110000.0, "delta_dps": 5000.0,
         "delta_percent": 4.76, "stddev": 1500, "iterations": 10000, "within_error": False},
        {"rank": 2, "name": "mplus_268245_chest", "dps": 101000.0, "delta_dps": 1000.0,
         "delta_percent": 0.95, "stddev": 1500, "iterations": 10000, "within_error": True},
    ],
    "baseline_dps": 105000.0,
    "simc_version": "1210-01",
    "wow_build": "12.1.0.69587",
    "content_version": "raid:1320;season:18",
}


def test_render_creates_standalone_html(tmp_path):
    path = str(tmp_path / "r.html")
    html = render_report(
        {"name": "Testchar", "realm": "ravencrest", "spec": "arcane",
         "class": "Mage", "item_level": 310,
         "snapshot_time": "2026-09-03 12:00", "snapshot_source": "Blizzard Armory"},
        DATA, path,
    )
    assert os.path.exists(path)
    assert "Testchar" in html
    assert "110 000" in html or "110,000" in html or "110000" in html.replace("\u202f", " ")
    assert "simulation error" in html
    assert "raid" in html and "mplus" in html
    assert "±" in html  # within-error badge present


def test_render_empty_ranking_does_not_crash():
    html = render_report({"name": "X"}, {"ranking": [], "baseline_dps": 0}, 
                         str(__import__("tempfile").gettempdir()) + "/empty.html")
    assert "Current DPS" in html
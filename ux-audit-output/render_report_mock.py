from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("app/templates"))


def _row(**kw):
    d = {"rank": 1, "name": "raid_1", "item_name": "Shellbound Bracers", "item_id": 11,
         "slot": "wrist", "slot_label": "Wrist", "source": "raid",
         "source_label": "Raid mythic", "boss": "The Lost Explorers",
         "ilvl": 334, "bonus_ids": "6652/12854", "replaces": "Bindings of the Risen",
         "replaces_item_id": 22, "replaces_ilvl": 315, "quality": "epic", "stats": "",
         "dps_fmt": "37 374", "median_fmt": "37 370", "delta_fmt": "48",
         "pct_fmt": "0.13", "err_pct": "2.89", "std_fmt": "1 078",
         "iterations": 10000, "within_error": True, "bar_pct": 100, "gain": True}
    d.update(kw)
    return d


rows = [_row(),
        _row(rank=2, name="mplus_2", item_name="Crown of the Eternal Fang",
             item_id=33, source="mplus", source_label="Mythic+ great vault",
             slot="head", slot_label="Head", boss="Nek'zali the Soulcoiler",
             replaces="Hood of the Old God", replaces_item_id=44,
             replaces_ilvl=310, within_error=False, bar_pct=60,
             delta_fmt="29", pct_fmt="0.08", dps_fmt="37 355"),
        _row(rank=3, name="raid_3", item_name="Fang Wristguards", item_id=55,
             boss="The Lost Explorers", replaces="Bindings of the Risen",
             replaces_item_id=22, replaces_ilvl=315, within_error=False,
             bar_pct=40, delta_fmt="19", pct_fmt="0.05", dps_fmt="37 345")]
html = env.get_template("report_detail.html").render(
    user={"battletag": "Calipse#2205"},
    character={"name": "Calipse", "realm": "shadowsong",
               "spec": "Demonology", "item_level": 317},
    snapshot_time="2026-09-03 22:17 UTC", snapshot_source="Blizzard Armory",
    simulated_at="2026-09-04 10:05 UTC",
    simc_version="1210-01", wow_build="12.1.0.69587",
    content_version="raid:1320;season:18", baseline_fmt="37 326",
    best={"pct": "0.13", "dps": "48", "name": "Shellbound Bracers",
          "boss": "The Lost Explorers", "ilvl": 334},
    top3=rows[:3], rows=rows,
    slots=[("head", "Head"), ("wrist", "Wrist")], warning=None,
    fight={"style": "Patchwerk", "kind": "Single Target", "duration": 300,
           "iterations": 1000, "target_error": 0.05,
           "wiki": "https://example.invalid/wiki"},
    talents={"spec": "Demonology", "hero": "Diabolist", "code": "CODE123",
             "armory_url": "https://example.invalid/armory"})
open("ux-audit-output/report.html", "w", encoding="utf-8").write(
    html.replace("/static/app.css", "app.css"))
print("report mock ok")

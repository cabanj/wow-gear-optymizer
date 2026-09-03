"""View helpers for dashboard / reports pages (enriched, display-ready dicts)."""
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blizzard.client import BlizzardClient
from ..db.models import BlizzardAccount, Character, CharacterSnapshot, SimulationResult, SimulationRun
from ..loot.discovery import item_icon, item_metadata
from .service import build_report_data

GEAR_ORDER = ["HEAD", "NECK", "SHOULDER", "BACK", "CHEST", "WRIST", "HANDS",
              "WAIST", "LEGS", "FEET", "FINGER_1", "FINGER_2",
              "TRINKET_1", "TRINKET_2", "MAIN_HAND", "OFF_HAND"]


async def character_gear(db: AsyncSession, character_id) -> list[dict]:
    """Equipped items by slot for the character page.

    Prefers the current snapshot; simc_addon_import snapshots carry no
    equipment JSON, so fall back to the latest armory snapshot.
    """
    snaps = (await db.execute(select(CharacterSnapshot).where(
        CharacterSnapshot.character_id == character_id
    ).order_by(CharacterSnapshot.timestamp.desc()))).scalars().all()
    equipment = None
    for s in snaps:
        eq = (s.raw or {}).get("equipment")
        if eq and eq.get("equipped_items"):
            equipment = eq
            break
    if not equipment:
        return []
    gear = []
    for it in equipment.get("equipped_items", []):
        slot = (it.get("slot") or {}).get("type", "")
        item = it.get("item") or {}
        item_id = item.get("id")
        if not item_id or slot not in GEAR_ORDER:
            continue
        q = (it.get("quality") or {}).get("type", "").lower()
        gems = []
        for g in it.get("gems", []) or []:
            gi = g.get("item") or {}
            gems.append(gi.get("name") or f"gem {gi.get('id', '?')}")
        ench = ""
        for e in it.get("enchantments", []) or []:
            ench = e.get("display_string") or e.get("name") or ""
            if ench:
                break
        gear.append({
            "slot": slot, "slot_label": SLOT_LABELS.get(slot.lower().replace("_1", "1").replace("_2", "2"), slot.title()),
            "item_id": item_id,
            "name": it.get("name") or item.get("name") or f"Item {item_id}",
            "ilvl": (it.get("level") or {}).get("value") or "?",
            "quality": {"epic": "epic", "rare": "rare", "uncommon": "uncommon",
                        "legendary": "legendary", "artifact": "legendary",
                        "heirloom": "rare"}.get(q, ""),
            "icon": await item_icon(db, item_id),
            "gems": gems,
            "enchant": ench,
        })
    gear.sort(key=lambda g: GEAR_ORDER.index(g["slot"]))
    return gear

CLASS_COLORS = {
    "Warrior": "#C79C6E", "Paladin": "#F58CBA", "Hunter": "#ABD473",
    "Rogue": "#FFF569", "Priest": "#FFFFFF", "Death Knight": "#C41F3B",
    "Shaman": "#0070DE", "Mage": "#69CCF0", "Warlock": "#9482C9",
    "Monk": "#00FF96", "Druid": "#FF7D0A", "Demon Hunter": "#A330C9",
    "Evoker": "#33937F",
}

SLOT_LABELS = {
    "head": "Head", "shoulder": "Shoulder", "chest": "Chest", "back": "Back",
    "wrist": "Wrist", "hands": "Hands", "waist": "Waist", "legs": "Legs",
    "feet": "Feet", "neck": "Neck", "finger1": "Finger", "finger2": "Finger",
    "trinket1": "Trinket", "trinket2": "Trinket", "main_hand": "Weapon",
    "off_hand": "Off-hand",
}


def _fmt(n) -> str:
    return f"{float(n):,.0f}".replace(",", " ")


def _parse_worn(profile_text: str | None) -> dict[str, str]:
    """slot -> item display name from a simc profile text."""
    worn = {}
    if not profile_text:
        return worn
    for line in profile_text.splitlines():
        m = re.match(r"^(\w+)=([^,]+),id=(\d+)", line.strip())
        if m and m.group(1) in SLOT_LABELS:
            worn[m.group(1)] = m.group(2).replace("_", " ")
    return worn


async def _quality(db: AsyncSession, item_id: int) -> str:
    try:
        meta = await item_metadata(db, item_id)
        q = (meta.get("quality") or {}).get("type", "").lower()
        return {"epic": "epic", "rare": "rare", "uncommon": "uncommon",
                "legendary": "legendary", "artifact": "legendary"}.get(q, "")
    except Exception:
        return ""


async def run_report(db: AsyncSession, run_id) -> dict:
    """Full enriched report for the detail page."""
    run = (await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))).scalar_one()
    char = (await db.execute(select(Character).where(Character.id == run.character_id))).scalar_one()
    snap = (await db.execute(select(CharacterSnapshot).where(
        CharacterSnapshot.id == run.snapshot_id))).scalar_one()
    data = await build_report_data(db, run.id)

    cfg = run.simulation_config or {}
    cand_by_name = {c["profileset"]: c for c in cfg.get("candidates", [])}
    worn = _parse_worn((snap.raw.get("parsed") or {}).get("profile_text"))

    # equipment names from armory snapshots (fallback for replaces)
    if not worn and snap.raw.get("equipment"):
        for it in snap.raw["equipment"].get("equipped_items", []):
            slot = (it.get("slot") or {}).get("type", "").lower()
            if slot in SLOT_LABELS:
                worn[slot] = (it.get("name") or (it.get("item") or {}).get("name") or "?")

    rows = []
    max_delta = max([r["delta_dps"] for r in data["ranking"]] + [1])
    last_boss = None
    for r in data["ranking"]:
        c = cand_by_name.get(r["name"], {})
        slot = (c.get("slot") or r["name"].split("_")[-1])
        boss = c.get("boss_or_dungeon") or "—"
        group = None
        if boss != last_boss:
            group, last_boss = boss, boss
        rows.append({
            "rank": r["rank"], "name": r["name"],
            "item_name": c.get("name") or r["name"],
            "item_id": c.get("item_id") or 0,
            "slot": slot, "slot_label": SLOT_LABELS.get(slot, slot),
            "source": "mplus" if r["name"].startswith("mplus") else "raid",
            "source_label": ("Mythic+ " + (c.get("variant") or "")).strip()
                            if r["name"].startswith("mplus")
                            else ("Raid " + (c.get("difficulty") or "")).strip(),
            "boss": boss, "group": group,
            "ilvl": c.get("item_level") or "?",
            "bonus_ids": "/".join(map(str, c.get("bonus_ids") or [])) or "—",
            "replaces": worn.get(slot, "?"),
            "quality": await _quality(db, c.get("item_id") or 0),
            "stats": "",
            "dps_fmt": _fmt(r["dps"]), "median_fmt": _fmt(data["ranking"] and r.get("dps", 0)),
            "delta_fmt": _fmt(r["delta_dps"]), "pct_fmt": f"{r['delta_percent']:.2f}",
            "std_fmt": _fmt(r["stddev"]), "iterations": r["iterations"],
            "within_error": r["within_error"],
            "bar_pct": round(r["delta_dps"] / max_delta * 100) if max_delta > 0 else 0,
        })

    return {
        "character": {"name": char.name, "realm": char.realm_slug,
                      "class": char.class_name, "spec": char.active_spec_name,
                      "item_level": float(snap.item_level) if snap.item_level else None},
        "snapshot_time": snap.timestamp.strftime("%Y-%m-%d %H:%M UTC"),
        "snapshot_source": "SimC addon import" if snap.source == "simc_addon_import"
                           else "Blizzard Armory",
        "simc_version": run.simc_version, "wow_build": run.wow_build,
        "content_version": run.content_version,
        "baseline_fmt": _fmt(data["baseline_dps"] or 0),
        "best": ({"pct": f"{rows[0]['pct_fmt']}", "dps": rows[0]["delta_fmt"],
                  "name": rows[0]["item_name"]} if rows else None),
        "rows": rows,
        "slots": sorted({row["slot_label"] for row in rows}),
    }


async def list_runs(db: AsyncSession, user_id, character_id=None) -> list[dict]:
    q = (select(SimulationRun, Character)
         .join(Character, SimulationRun.character_id == Character.id)
         .join(BlizzardAccount, Character.blizzard_account_id == BlizzardAccount.id)
         .where(BlizzardAccount.user_id == user_id,
                SimulationRun.status == "completed")
         .order_by(SimulationRun.finished_at.desc()))
    if character_id:
        q = q.where(Character.id == character_id)
    out = []
    for run, char in (await db.execute(q)).all():
        res = (await db.execute(select(SimulationResult).where(
            SimulationResult.simulation_run_id == run.id))).scalars().all()
        base = next((float(r.mean) for r in res if r.profileset_name is None), None)
        cands = [r for r in res if r.profileset_name is not None]
        best = None
        if base and cands:
            b = max(cands, key=lambda r: float(r.mean))
            d = float(b.mean) - base
            best = {"name": b.profileset_name, "dps": _fmt(d),
                    "pct": f"{d / base * 100:.2f}"}
        out.append({
            "id": str(run.id), "character_name": char.name,
            "profile_type": (run.simulation_config or {}).get("profile_type", "?"),
            "created_at": (run.finished_at or run.created_at).strftime("%Y-%m-%d %H:%M"),
            "baseline": _fmt(base or 0), "best": best,
            "simc_version": run.simc_version, "content_version": run.content_version,
        })
    return out


async def history(db: AsyncSession, character_id) -> tuple[list, list]:
    """(labels, baseline values) for the Chart.js history graph."""
    q = (select(SimulationRun).where(SimulationRun.character_id == character_id,
                                     SimulationRun.status == "completed")
         .order_by(SimulationRun.finished_at.asc()))
    labels, values = [], []
    for run in (await db.execute(q)).scalars().all():
        res = (await db.execute(select(SimulationResult).where(
            SimulationResult.simulation_run_id == run.id,
            SimulationResult.profileset_name.is_(None)))).scalars().first()
        if res is not None:
            labels.append((run.finished_at or run.created_at).strftime("%m-%d"))
            values.append(round(float(res.mean)))
    return labels, values


async def dashboard_cards(db: AsyncSession, user_id) -> list[dict]:
    chars = (await db.execute(
        select(Character, BlizzardAccount).join(BlizzardAccount)
        .where(BlizzardAccount.user_id == user_id)
        .order_by(Character.name))).all()
    cards = []
    for char, _acc in chars:
        runs = await list_runs(db, user_id, str(char.id))
        snap = (await db.execute(select(CharacterSnapshot).where(
            CharacterSnapshot.character_id == char.id,
            CharacterSnapshot.is_current.is_(True)))).scalars().first()
        cards.append({
            "id": str(char.id), "name": char.name, "realm": char.realm_slug,
            "class": char.class_name, "spec": char.active_spec_name,
            "class_color": CLASS_COLORS.get(char.class_name or "", "#e8e6e3"),
            "item_level": float(snap.item_level) if snap and snap.item_level else None,
            "snapshot_time": snap.timestamp.strftime("%Y-%m-%d %H:%M") if snap else None,
            "best": runs[0]["best"] if runs and runs[0]["best"] else None,
        })
    return cards


async def add_character_manual(db: AsyncSession, account: BlizzardAccount,
                               realm: str, name: str) -> dict:
    """Create character by realm+name and snapshot via Profile API."""
    from ..characters.service import snapshot_character
    realm = realm.lower().strip().replace(" ", "-")
    name = name.strip()
    char = (await db.execute(select(Character).where(
        Character.region == account.region, Character.realm_slug == realm,
        Character.name.ilike(name)))).scalar_one_or_none()
    if char is None:
        char = Character(blizzard_account_id=account.id, region=account.region,
                         realm_slug=realm, name=name, selected=True)
        db.add(char)
        await db.flush()
    else:
        char.selected = True
    snap = await snapshot_character(db, char, account)
    return {"id": str(char.id), "name": char.name,
            "item_level": float(snap.item_level) if snap.item_level else None}

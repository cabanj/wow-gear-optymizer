"""Orchestration: character snapshot → candidates → simulation runs → report data."""
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..blizzard.cache import cache_key, get_cached, set_cached
from ..config import get_settings
from ..db.models import Character, CharacterSnapshot, Report, SimulationResult, SimulationRun
from ..loot.candidates import CandidateItem, generate_candidates, mark_raid_encounters
from ..loot.discovery import detect_current_content
from ..loot.upgrade_rules import TrackPolicy
from ..simc.profile_builder import Candidate, build_profileset_input
from ..simc.parser import compute_ranking, extract_results, extract_version, parse_json2


def _to_builder_candidate(c: CandidateItem, worn: dict) -> Candidate:
    w = worn.get(c.slot, {})
    return Candidate(
        item_id=c.item_id, name=c.name, slot=c.slot, item_level=c.item_level,
        bonus_ids=c.bonus_ids,
        gems=w.get("gems", []),            # decision: identical gems to replaced item
        enchant_id=w.get("enchant_id"),    # decision: identical enchant
        replace_slot=c.slot,
        source=c.source, boss_or_dungeon=c.boss_or_dungeon,
        upgrade_track=c.difficulty,
        pset=c.pset,
        off_item_id=c.off_item_id, off_name=c.off_name,
        off_bonus_ids=c.off_bonus_ids or [],
        off_ilevel=c.off_ilvl,
    )


async def run_full_simulation(
    db: AsyncSession,
    character: Character,
    snapshot: CharacterSnapshot,
    profile_type: str,   # "raid" | "mplus"
) -> uuid.UUID:
    """Create a SimulationRun with generated profile; the simulator worker executes it."""
    s = get_settings()
    # Re-fetch snapshot: callers may hold a stale object (expire_on_commit=False)
    snapshot = (await db.execute(
        select(CharacterSnapshot).where(CharacterSnapshot.id == snapshot.id)
    )).scalar_one()

    # 1. current content (cached via api_cache by discovery functions)
    content = await detect_current_content(db)
    mark_raid_encounters([e.id for e in content.raid_encounters])

    # 2. season seed
    seed_path = "/data/seed/season-seed-midnight-s2.json"  # mounted in compose
    import os
    if not os.path.exists(seed_path):
        seed_path = os.path.join("docs", "season-seed-midnight-s2.json")
    policy = TrackPolicy.load(seed_path)

    # 3. worn items from snapshot (keys normalized to canonical simc slots,
    # e.g. FINGER_1 -> finger1 — candidates.py and the gem/enchant swap rely on it)
    from ..simc.profile_builder import SLOT_MAP
    equipment = snapshot.raw.get("equipment", {})
    worn: dict[str, dict] = {}
    for item in equipment.get("equipped_items", []):
        slot = (item.get("slot") or {}).get("type", "")
        canon = SLOT_MAP.get(slot, slot.lower())
        it = item.get("item", {})
        bonus_ids = [b for b in (it.get("bonus_ids") or []) if b != 6652]
        gems = [g.get("item", {}).get("id") for g in item.get("gems", []) if g.get("item")]
        worn[canon] = {
            "item_id": it.get("id"),
            "item_level": (it.get("level") or {}).get("value"),
            "bonus_ids": bonus_ids,
            "gems": [f"{g}" for g in gems if g],
            "enchant_id": (item.get("enchant") or {}).get("id") if item.get("enchant") else None,
        }

    # 4. candidates
    encounter_ids = {e.id: e.name for e in content.raid_encounters}
    # TODO phase 6: mplus dungeon encounters from season dungeon pool
    candidates = await generate_candidates(
        db, encounter_ids, worn, policy,
        max_per_slot=s.max_candidates_per_slot,
        class_name=character.class_name or "",
    )
    builder_cands = [_to_builder_candidate(c, worn) for c in candidates]

    # 5. build profile input
    sim_config = {
        "iterations": s.raid_sim_iterations if profile_type == "raid" else s.mplus_sim_iterations,
        "target_error": s.raid_target_error if profile_type == "raid" else s.mplus_target_error,
        "fight_style": s.raid_fight_style if profile_type == "raid" else s.mplus_fight_style,
        "duration": s.raid_duration if profile_type == "raid" else s.mplus_duration,
        "threads": 4,
        "profileset_work_threads": 2,
    }
    profile = build_profileset_input(snapshot.raw, builder_cands, profile_type, sim_config,
                                     fallback_realm=character.realm_slug,
                                     fallback_name=character.name)

    # 6. create run (persist candidate metadata for the report pages)
    run = SimulationRun(
        character_id=character.id, snapshot_id=snapshot.id,
        simulation_config={**sim_config, "profile_type": profile_type,
                           "candidates": [
                               {"profileset": c.pset or f"{c.source}_{c.item_id}_{c.slot}",
                                "item_id": c.item_id, "name": c.name, "slot": c.slot,
                                "item_level": c.item_level,
                                "bonus_ids": c.bonus_ids, "source": c.source,
                                "difficulty": c.difficulty, "variant": c.variant,
                                "boss_or_dungeon": c.boss_or_dungeon,
                                "inventory_type": c.inventory_type,
                                "off_item_id": c.off_item_id, "off_name": c.off_name,
                                "off_ilvl": c.off_ilvl}
                               for c in candidates
                           ]},
        profile=profile, status="pending",
        content_version=f"raid:{content.raid_instance_id};season:{content.mplus_season_id}",
    )
    db.add(run)
    await db.commit()
    return run.id


async def purge_old_data(db: AsyncSession, days: int = 3) -> dict:
    """Keep only recent history: delete reports/runs/results older than `days`.

    Order matters (reports reference runs via FK): reports → results → runs.
    """
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rep = await db.execute(select(Report).where(Report.generated_at < cutoff))
    n_rep = 0
    for r in rep.scalars().all():
        await db.delete(r)
        n_rep += 1
    res = await db.execute(
        select(SimulationResult).join(SimulationRun)
        .where(SimulationRun.finished_at < cutoff))
    n_res = 0
    for row in res.scalars().all():
        await db.delete(row)
        n_res += 1
    runs = await db.execute(
        select(SimulationRun)
        .where(SimulationRun.finished_at < cutoff,
               SimulationRun.status.in_(("completed", "failed"))))
    n_runs = 0
    for row in runs.scalars().all():
        # never orphan a report: reports were deleted above if old enough
        await db.delete(row)
        n_runs += 1
    await db.commit()
    return {"reports": n_rep, "results": n_res, "runs": n_runs}


async def build_report_data(db: AsyncSession, run_id: uuid.UUID) -> dict:
    """Read results for a completed run and compute ranking."""
    run = (await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))).scalar_one()
    results = (await db.execute(
        select(SimulationResult).where(SimulationResult.simulation_run_id == run_id)
    )).scalars().all()

    from ..simc.parser import ProfileResult
    prs = [ProfileResult(
        name=r.profileset_name or "Baseline",
        dps_mean=float(r.mean), dps_median=float(r.median),
        dps_min=float(r.min), dps_max=float(r.max),
        dps_stddev=float(r.stddev), iterations=r.iterations,
        error=(r.confidence_interval or {}).get("error"),
    ) for r in results]
    ranking = compute_ranking(prs)
    # report shows actual upgrades only — downgrades/sidegrades are noise
    ranking = [r for r in ranking if r["delta_dps"] > 0]
    for i, row in enumerate(ranking, 1):
        row["rank"] = i
    return {
        "run_id": str(run_id),
        "simc_version": run.simc_version,
        "wow_build": run.wow_build,
        "content_version": run.content_version,
        "baseline_dps": next((float(r.mean) for r in results if r.profileset_name is None), None),
        "ranking": ranking,
    }

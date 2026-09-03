"""Orchestration: character snapshot → candidates → simulation runs → report data."""
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .blizzard.cache import cache_key, get_cached, set_cached
from .config import get_settings
from .db.models import Character, CharacterSnapshot, Report, SimulationResult, SimulationRun
from .loot.candidates import CandidateItem, generate_candidates, mark_raid_encounters
from .loot.discovery import detect_current_content
from .loot.upgrade_rules import TrackPolicy
from .simc.profile_builder import Candidate, build_profileset_input
from .simc.parser import compute_ranking, extract_results, extract_version, parse_json2


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
    )


async def run_full_simulation(
    db: AsyncSession,
    character: Character,
    snapshot: CharacterSnapshot,
    profile_type: str,   # "raid" | "mplus"
) -> uuid.UUID:
    """Create a SimulationRun with generated profile; the simulator worker executes it."""
    s = get_settings()

    # 1. current content (cached via api_cache by discovery functions)
    content = await detect_current_content(db)
    mark_raid_encounters([e.id for e in content.raid_encounters])

    # 2. season seed
    seed_path = s.report_path + "/season-seed.json"  # on VPS: mounted from repo docs/
    import os
    if not os.path.exists(seed_path):
        seed_path = os.path.join("docs", "season-seed-midnight-s2.json")
    policy = TrackPolicy.load(seed_path)

    # 3. worn items from snapshot
    equipment = snapshot.raw.get("equipment", {})
    worn: dict[str, dict] = {}
    for item in equipment.get("equipped_items", []):
        slot = (item.get("slot") or {}).get("type", "")
        it = item.get("item", {})
        bonus_ids = [b for b in (it.get("bonus_ids") or []) if b != 6652]
        gems = [g.get("item", {}).get("id") for g in item.get("gems", []) if g.get("item")]
        worn[slot] = {
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
        db, encounter_ids, worn, policy, max_per_slot=s.max_candidates_per_slot
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
    profile = build_profileset_input(snapshot.raw, builder_cands, profile_type, sim_config)

    # 6. create run
    run = SimulationRun(
        character_id=character.id, snapshot_id=snapshot.id,
        simulation_config=sim_config, profile=profile, status="pending",
        content_version=f"raid:{content.raid_instance_id};season:{content.mplus_season_id}",
    )
    db.add(run)
    await db.commit()
    return run.id


async def build_report_data(db: AsyncSession, run_id: uuid.UUID) -> dict:
    """Read results for a completed run and compute ranking."""
    run = (await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))).scalar_one()
    results = (await db.execute(
        select(SimulationResult).where(SimulationResult.simulation_run_id == run_id)
    )).scalars().all()

    from .simc.parser import ProfileResult
    prs = [ProfileResult(
        name=r.profileset_name or "Baseline",
        dps_mean=float(r.mean), dps_median=float(r.median),
        dps_min=float(r.min), dps_max=float(r.max),
        dps_stddev=float(r.stddev), iterations=r.iterations,
        error=(r.confidence_interval or {}).get("error"),
    ) for r in results]
    ranking = compute_ranking(prs)
    return {
        "run_id": str(run_id),
        "simc_version": run.simc_version,
        "wow_build": run.wow_build,
        "content_version": run.content_version,
        "baseline_dps": next((float(r.mean) for r in results if r.profileset_name is None), None),
        "ranking": ranking,
    }

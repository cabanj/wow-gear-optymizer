"""Parse SimulationCraft json2 output into structured results."""
import json
from dataclasses import dataclass


@dataclass
class ProfileResult:
    name: str  # profileset name, or "Baseline"
    dps_mean: float
    dps_median: float
    dps_min: float
    dps_max: float
    dps_stddev: float
    iterations: int
    error: float | None  # target_error actually achieved if reported


def parse_json2(text: str) -> dict:
    return json.loads(text)


def extract_results(data: dict) -> list[ProfileResult]:
    """json2 shape (verified against SimC 1210-01 / WoW 12.1.0):
    - baseline player: sim.players[0].collected_data.dps
    - profilesets: sim.profilesets.results[] with name/mean/median/min/max/
      stddev/mean_stddev/mean_error/iterations
    """
    results = []
    for player in data.get("sim", {}).get("players", []):
        cd = player.get("collected_data") or {}
        dps = cd.get("dps") or {}
        if not dps:
            continue
        results.append(ProfileResult(
            name=player.get("name", "?"),
            dps_mean=float(dps.get("mean", 0)),
            dps_median=float(dps.get("median", 0)),
            dps_min=float(dps.get("min", 0)),
            dps_max=float(dps.get("max", 0)),
            dps_stddev=float(dps.get("std_dev", 0)),
            iterations=int(dps.get("iterations", cd.get("iterations", 0))),
            error=dps.get("error"),
        ))
    ps = data.get("sim", {}).get("profilesets") or {}
    for r in ps.get("results", []):
        results.append(ProfileResult(
            name=r.get("name", "?"),
            dps_mean=float(r.get("mean", 0)),
            dps_median=float(r.get("median", 0)),
            dps_min=float(r.get("min", 0)),
            dps_max=float(r.get("max", 0)),
            dps_stddev=float(r.get("stddev", 0)),
            iterations=int(r.get("iterations", 0)),
            error=r.get("mean_error"),
        ))
    return results


def extract_version(data: dict) -> dict:
    d = data  # version info lives at top level, not under sim
    sim = data.get("sim", {})
    return {
        "simc_version": d.get("version"),
        "simc_commit": d.get("git_revision"),
        "git_branch": d.get("git_branch"),
        "wow_build": sim.get("build_level") or d.get("build_date"),
        "target_error": sim.get("options", {}).get("target_error"),
        "iterations": sim.get("options", {}).get("iterations"),
    }


def compute_ranking(results: list[ProfileResult]) -> list[dict]:
    """Baseline + deltas sorted desc. delta_percent = (cand-base)/base*100."""
    baseline = next((r for r in results if r.name == "Baseline"), None)
    if baseline is None:
        raise ValueError("no baseline in results")
    base = baseline.dps_mean
    out = []
    for r in results:
        if r is baseline:
            continue
        delta = r.dps_mean - base
        out.append({
            "name": r.name,
            "dps": r.dps_mean,
            "delta_dps": delta,
            "delta_percent": (delta / base * 100) if base else 0.0,
            "stddev": r.dps_stddev,
            "iterations": r.iterations,
            "within_error": abs(delta) < 2 * r.dps_stddev,
        })
    out.sort(key=lambda x: x["delta_dps"], reverse=True)
    for i, row in enumerate(out, 1):
        row["rank"] = i
    return out

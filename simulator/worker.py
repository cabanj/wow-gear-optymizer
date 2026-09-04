"""Simulator worker: runs inside the simulationcraftorg/simc container.

Polls the simulation_runs table for pending jobs, writes simc input to /work,
runs simc, parses json2, stores results into Postgres via psycopg2-binary
(installed at container start — the simc image lacks pg drivers).
"""
import json
import os
import re
import subprocess
import sys
import time
import uuid

SIMC = os.environ.get("SIMC_PATH", "/app/SimulationCraft/simc")
WORK = os.environ.get("SIM_WORK", "/work")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "10"))
DB_URL = os.environ.get("DATABASE_URL", "postgresql://wow:wow@postgres:5432/wow")
TIMEOUT = int(os.environ.get("SIM_TIMEOUT_SECONDS", "3600"))

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--break-system-packages", "psycopg2-binary"], check=False)
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise SystemExit("psycopg2 unavailable; cannot run worker")


def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def claim_run(conn):
    """Atomically claim one pending run (FOR UPDATE SKIP LOCKED)."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE simulation_runs SET status='running', started_at=now()
            WHERE id = (
                SELECT id FROM simulation_runs WHERE status='pending'
                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            RETURNING id, profile, simulation_config
        """)
        row = cur.fetchone()
        return dict(row) if row else None


def detect_simc_version() -> dict:
    """SimC prints version banner on any invocation; grab from a no-op run."""
    proc = subprocess.run([SIMC], input="", capture_output=True, text=True, timeout=60)
    import re
    m = re.search(r"SimulationCraft (\S+) for World of Warcraft (\S+)", proc.stdout + proc.stderr)
    g = re.search(r"git build (\S+) (\w+)", proc.stdout + proc.stderr)
    return {
        "simc_version": m.group(1) if m else "unknown",
        "wow_build": m.group(2) if m else "unknown",
        "git_branch": g.group(1) if g else None,
        "simc_commit": g.group(2) if g else None,
    }


def run_simc(run_id: str, profile: str) -> str:
    os.makedirs(WORK, exist_ok=True)
    input_path = os.path.join(WORK, f"{run_id}.simc")
    output_path = os.path.join(WORK, f"{run_id}.json")
    # SimC cannot parse inline local_json={...} (it mangles the JSON into an
    # armory spec -> "Invalid region"). Extract to a sidecar file instead.
    m = re.search(r"^local_json=(\{.*\})\s*$", profile, re.M)
    if m:
        armory_path = os.path.join(WORK, f"{run_id}.armory.json")
        with open(armory_path, "w") as f:
            f.write(m.group(1))
        profile = profile[:m.start()] + f"local_json={armory_path}\n" + profile[m.end():]
    with open(input_path, "w") as f:
        f.write(profile)
        f.write(f"\njson2={output_path}\n")
    proc = subprocess.run([SIMC, input_path], capture_output=True, text=True,
                          timeout=TIMEOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"simc exit {proc.returncode}: {proc.stderr[-2000:]}")
    with open(output_path) as f:
        return f.read()


def store_results(conn, run_id: str, json2_text: str) -> None:
    data = json.loads(json2_text)
    ver = extract_version(data)
    sim = data.get("sim", {})

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE simulation_runs
            SET simc_version=%s, simc_commit=%s, wow_build=%s,
                status='completed', finished_at=now()
            WHERE id=%s
        """, (ver["simc_version"], ver.get("simc_commit"), ver.get("wow_build"), run_id))

        # baseline player (compact raw: full player blob is ~1MB, keep essentials)
        for player in sim.get("players", []):
            cd = player.get("collected_data") or {}
            dps = cd.get("dps") or {}
            if not dps:
                continue
            slim = {"name": player.get("name"),
                    "specialization": player.get("specialization"),
                    "collected_data": cd,
                    "gear": player.get("gear"),
                    "talents": player.get("talents")}
            cur.execute("""
                INSERT INTO simulation_results
                (id, simulation_run_id, profileset_name, profile_type, mean, median,
                 min, max, stddev, iterations, confidence_interval, raw)
                VALUES (%s,%s,NULL,'raid',%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                str(uuid.uuid4()),
                run_id,
                dps.get("mean", 0), dps.get("median", 0),
                dps.get("min", 0), dps.get("max", 0), dps.get("std_dev", 0),
                dps.get("iterations", 0) or sim.get("options", {}).get("iterations", 0),
                json.dumps({"error": dps.get("error")}),
                json.dumps(slim),
            ))

        # profilesets
        for r in (sim.get("profilesets") or {}).get("results", []):
            name = r.get("name", "")
            ptype = "mplus" if name.startswith("mplus") else "raid"
            cur.execute("""
                INSERT INTO simulation_results
                (id, simulation_run_id, profileset_name, profile_type, mean, median,
                 min, max, stddev, iterations, confidence_interval, raw)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                str(uuid.uuid4()),
                run_id, name, ptype,
                r.get("mean", 0), r.get("median", 0),
                r.get("min", 0), r.get("max", 0), r.get("stddev", 0),
                r.get("iterations", 0),
                json.dumps({"mean_error": r.get("mean_error"),
                            "mean_stddev": r.get("mean_stddev")}),
                json.dumps(r),
            ))


def extract_version(data: dict) -> dict:
    return {
        "simc_version": data.get("version"),
        "wow_build": data.get("build_date"),
        "simc_commit": data.get("git_revision"),
    }


def fail_run(conn, run_id: str, error_msg: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE simulation_runs SET status='failed', error=%s, finished_at=now()
            WHERE id=%s
        """, (error_msg[:4000], run_id))


def main():
    conn = get_conn()
    conn.autocommit = False
    ver = detect_simc_version()
    print("simulator worker started; simc:", ver, flush=True)
    while True:
        run = claim_run(conn)
        conn.commit()
        if not run:
            time.sleep(POLL_SECONDS)
            continue
        run_id = str(run["id"])
        print("running", run_id, flush=True)
        try:
            json2_text = run_simc(run_id, run["profile"])
            conn2 = get_conn()
            store_results(conn2, run_id, json2_text)
            conn2.commit()
            conn2.close()
            print("completed", run_id, flush=True)
        except Exception as e:
            conn2 = get_conn()
            fail_run(conn2, run_id, str(e))
            conn2.commit()
            conn2.close()
            print("failed", run_id, str(e)[:300], flush=True)
        # loop again with fresh connection


if __name__ == "__main__":
    main()
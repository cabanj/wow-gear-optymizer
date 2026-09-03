"""Simulator worker: runs inside the simulationcraftorg/simc container.

Polls the simulation_runs table for pending jobs, writes simc input to /work,
runs simc, parses json2, stores results. Uses psycopg2 (sync — fine here).
"""
import json
import os
import subprocess
import time
import uuid

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_URL", "postgresql://wow:wow@postgres:5432/wow")
SIMC = os.environ.get("SIMC_PATH", "/usr/local/bin/simc")
WORK = "/work"
POLL_SECONDS = 10


def get_conn():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.real_dictcursor)


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
        return cur.fetchone()


def detect_simc_version():
    out = subprocess.run([SIMC, "--version"], capture_output=True, text=True, timeout=60)
    return out.stdout.strip() or out.stderr.strip()


def run_simc(run_id: str, profile: str) -> str:
    os.makedirs(WORK, exist_ok=True)
    input_path = f"{WORK}/{run_id}.simc"
    output_path = f"{WORK}/{run_id}.json"
    with open(input_path, "w") as f:
        f.write(profile)
        f.write(f"\njson2={output_path}\n")
    proc = subprocess.run([SIMC, input_path], capture_output=True, text=True,
                          timeout=int(os.environ.get("SIM_TIMEOUT_SECONDS", "3600")))
    if proc.returncode != 0:
        raise RuntimeError(f"simc exit {proc.returncode}: {proc.stderr[-2000:]}")
    with open(output_path) as f:
        return f.read()


def store_results(conn, run_id, version_info, json2_text):
    data = json.loads(json2_text)
    from_profile = version_info
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE simulation_runs
            SET simc_version=%s, wow_build=%s, status='completed', finished_at=now()
            WHERE id=%s
        """, (version_info.get("simc_version"), version_info.get("wow_build"), run_id))
        for player in data.get("sim", {}).get("players", []):
            cd = player.get("collected_data") or {}
            dps = cd.get("dps") or {}
            if not dps:
                continue
            name = player.get("name")
            is_baseline = name == "Baseline"
            ptype = "raid" if (name == "Baseline" or name.startswith("raid")) else "mplus"
            cur.execute("""
                INSERT INTO simulation_results
                (simulation_run_id, profileset_name, profile_type, mean, median,
                 min, max, stddev, iterations, confidence_interval, raw)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                run_id,
                None if is_baseline else name,
                ptype,
                dps.get("mean", 0), dps.get("median", 0),
                dps.get("min", 0), dps.get("max", 0), dps.get("std_dev", 0),
                cd.get("iterations", 0),
                json.dumps({"error": dps.get("error")}),
                json.dumps(player)[:100000],
            ))


def fail_run(conn, run_id, error_msg):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE simulation_runs SET status='failed', error=%s, finished_at=now()
            WHERE id=%s
        """, (error_msg, run_id))


def main():
    conn = get_conn()
    conn.autocommit = False
    print("simulator worker started; simc:", detect_simc_version(), flush=True)
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
            store_results(conn2, run_id, {}, json2_text)
            conn2.commit()
            conn2.close()
            print("completed", run_id, flush=True)
        except Exception as e:
            conn2 = get_conn()
            fail_run(conn2, run_id, str(e)[:4000])
            conn2.commit()
            conn2.close()
            print("failed", run_id, e, flush=True)


if __name__ == "__main__":
    main()

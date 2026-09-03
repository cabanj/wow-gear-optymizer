"""Resolve $spellId placeholders in Blizzard effect descriptions to
ilvl-scaled values via `simc spell_query=spell.id=X@ILVL`.

Runs inside the simulator container (has the simc binary + DB access).
Reads pending requests from api_cache (key spellq:{spell_id}:{ilvl},
payload {"pending": true}), writes {"value": float, "duration": str|None}.
"""
import json
import os
import re
import subprocess
import sys

SIMC = os.environ.get("SIMC_PATH", "/app/SimulationCraft/simc")
DB_URL = os.environ.get("DATABASE_URL", "postgresql://wow:wow@postgres:5432/wow")

try:
    import psycopg2
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet",
                    "--break-system-packages", "psycopg2-binary"], check=False)
    import psycopg2


def query_spell(spell_id: int, ilvl: int) -> dict:
    """Run spell_query, follow trigger chain, return scaled values.

    Returns {'value': float|None, 'duration': str|None, 'rating': str|None}.
    """
    proc = subprocess.run(
        [SIMC], input=f"spell_query=spell.id={spell_id}@{ilvl}\n",
        capture_output=True, text=True, timeout=120)
    out = proc.stdout + proc.stderr
    effects = {}
    for m in re.finditer(r"#(\d+) \(id=\d+\)[^:]*:[^\n]*\n\s*Base Value:[^|]*\| Scaled Value:\s*([0-9.]+)",
                         out):
        effects[int(m.group(1))] = float(m.group(2))
    rating = None
    m = re.search(r"Rating:\s*(\w+)", out)
    if m:
        rating = m.group(1)
    dur = None
    m = re.search(r"^Duration\s*:\s*(.+)$", out, re.M)
    if m:
        dur = m.group(1).strip()
    trig = re.search(r"Trigger Spell:\s*(\d+)", out)
    if trig and not any(v for v in effects.values()):
        sub = query_spell(int(trig.group(1)), ilvl)
        return {"value": sub["value"], "duration": sub["duration"] or dur,
                "rating": sub["rating"] or rating}
    return {"value": effects.get(1), "duration": dur, "rating": rating}


def main(limit: int = 50) -> None:
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("""
            SELECT key FROM api_cache
            WHERE key LIKE 'spellq:%%' AND payload->>'pending' = 'true'
            LIMIT %s
        """, (limit,))
        pending = [r[0] for r in cur.fetchall()]
    print(f"pending spell queries: {len(pending)}", flush=True)
    for key in pending:
        try:
            _, sid, ilvl = key.split(":")
            res = query_spell(int(sid), int(ilvl))
            if res["value"] is None:
                print(f"  {key}: no scaled values", flush=True)
                continue
            payload = {"value": res["value"], "duration": res["duration"],
                       "rating": res["rating"]}
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO api_cache (key, payload, fetched_at, ttl_seconds)
                    VALUES (%s, %s, extract(epoch from now()), %s)
                    ON CONFLICT (key) DO UPDATE
                      SET payload = %s, fetched_at = extract(epoch from now())
                """, (key, json.dumps(payload), 30 * 86400, json.dumps(payload)))
            print(f"  {key}: {payload['value']} ({payload['duration']})", flush=True)
        except Exception as e:
            print(f"  {key}: ERROR {e}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()

"""Self-contained HTML report generation."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

SLOT_LABELS = {
    "head": "Head", "shoulder": "Shoulder", "chest": "Chest", "back": "Back",
    "wrist": "Wrist", "hands": "Hands", "waist": "Waist", "legs": "Legs",
    "feet": "Feet", "neck": "Neck", "finger1": "Finger", "finger2": "Finger",
    "trinket1": "Trinket", "trinket2": "Trinket", "main_hand": "Weapon",
    "off_hand": "Off-hand",
}


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


def render_report(character: dict, report_data: dict, path: str) -> str:
    """Build a standalone responsive HTML report."""
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows = []
    for r in report_data["ranking"]:
        source = "Raid" if r["name"].startswith("raid") else "M+"
        slot = r["name"].split("_")[-1] if "_" in r["name"] else "?"
        slot_label = SLOT_LABELS.get(slot, slot.title())
        badge = ' <span class="warn" title="difference within 2 stddev">±</span>' if r["within_error"] else ""
        rows.append(f"""
<tr class="{'rank-1' if r['rank']==1 else ''}" data-source="{source.lower()}" data-slot="{slot}">
 <td>#{r['rank']}</td>
 <td><code>{r['name']}</code></td>
 <td>{slot_label}</td>
 <td>{source}</td>
 <td>{r['boss_or_dungeon'] if 'boss_or_dungeon' in r else '—'}</td>
 <td class="num">{_fmt(r['dps'])}</td>
 <td class="num up">+{_fmt(r['delta_dps'])}{badge}</td>
 <td class="num up">+{r['delta_percent']:.2f}%</td>
</tr>""")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{character['name']} — Gear Upgrade Report</title>
<style>
:root {{ color-scheme: dark; }}
body {{ font-family: system-ui, sans-serif; background:#12141a; color:#e8e6e3; margin:0; }}
main {{ max-width: 64rem; margin: 1.5rem auto; padding: 0 1rem; }}
h1 {{ font-size: 1.3rem; }} h2 {{ font-size: 1.05rem; margin-top: 1.6rem; }}
.meta {{ color:#9aa3b2; font-size: .85rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: .85rem; }}
th, td {{ border: 1px solid #2a3140; padding: .35rem .55rem; text-align: left; }}
th {{ background:#1b2130; cursor: pointer; user-select: none; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.up {{ color:#6fce7d; }} .warn {{ color:#e8b34a; }}
.rank-1 td {{ background:#14301c; }}
.filters button {{ margin: .15rem .2rem .15rem 0; padding:.25rem .7rem; background:#1b2130;
  color:#cfd6e4; border:1px solid #2a3140; border-radius:.3rem; cursor:pointer; }}
.filters button.on {{ background:#2f5fbe; color:#fff; border-color:#2f5fbe; }}
.cards {{ display:flex; gap:.8rem; flex-wrap:wrap; margin:1rem 0; }}
.card {{ background:#1b2130; border:1px solid #2a3140; border-radius:.5rem; padding:.8rem 1.1rem; }}
.card .v {{ font-size:1.25rem; font-weight:600; }}
.disclaimer {{ color:#9aa3b2; font-size:.8rem; margin-top:1.5rem; }}
@media (max-width:700px) {{ table {{ font-size:.72rem; }} th,td{{padding:.25rem .3rem;}} }}
</style></head><body><main>
<h1>{character['name']} — {character.get('realm','')} — {character.get('spec','')}</h1>
<p class="meta">
 Character: {character['name']} · {character.get('class','')} {character.get('spec','')} ·
 ilvl {character.get('item_level','?')}<br>
 Snapshot: {character.get('snapshot_time','?')} ({character.get('snapshot_source','Blizzard Armory')})<br>
 SimC {report_data.get('simc_version') or '?'} · WoW build {report_data.get('wow_build') or '?'} ·
 content {report_data.get('content_version') or '?'} · generated {gen_time}
</p>
<div class="cards">
 <div class="card"><div class="meta">Current DPS</div>
   <div class="v">{_fmt(report_data['baseline_dps'] or 0)}</div></div>
 <div class="card"><div class="meta">Best upgrade</div>
   <div class="v up">{f"#{1} {report_data['ranking'][0]['delta_percent']:.2f}% (+{_fmt(report_data['ranking'][0]['delta_dps'])})" if report_data['ranking'] else "—"}</div></div>
</div>
<h2>Ranking</h2>
<p class="filters" id="filters">
 <button class="on" data-f="all">All</button>
 <button data-f="raid">Raid</button>
 <button data-f="mplus">Mythic+</button>
</p>
<table id="tbl">
<thead><tr>
 <th data-s="num">Rank</th><th>Item</th><th>Slot</th><th>Source</th><th>Boss/Dungeon</th>
 <th data-s="num">DPS</th><th data-s="num">+ DPS</th><th data-s="num">+ %</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
<p class="disclaimer">Results are simulation estimates. Small differences may be within
simulation error. ± marks deltas within 2× standard deviation.</p>
<script>
// filters
document.querySelectorAll('#filters button').forEach(b => b.onclick = () => {{
  document.querySelectorAll('#filters button').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  const f = b.dataset.f;
  document.querySelectorAll('#tbl tbody tr').forEach(tr => {{
    tr.style.display = (f === 'all' || tr.dataset.source === f) ? '' : 'none';
  }});
}});
// sorting
document.querySelectorAll('#tbl th[data-s]').forEach((th, ti) => {{
  th.onclick = () => {{
    const tbody = document.querySelector('#tbl tbody');
    const rows = [...tbody.querySelectorAll('tr')];
    const num = th.dataset.s === 'num';
    rows.sort((a, b) => {{
      const av = a.children[ti].textContent.replace(/[^0-9.\\-]/g, '');
      const bv = b.children[ti].textContent.replace(/[^0-9.\\-]/g, '');
      return num ? bv - av : a.children[ti].textContent.localeCompare(b.children[ti].textContent);
    }});
    rows.forEach(r => tbody.appendChild(r));
  }};
}});
</script>
</main></body></html>"""
    Path(path).write_text(html, encoding="utf-8")
    return html

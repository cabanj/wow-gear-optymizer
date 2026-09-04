"""Embellishments: crafted-item bonus_id -> embellishment name + spell.

Seed: docs/embellishments.json, generated from SimC
engine/dbc/generated/embellishment_data.inc (54 entries, WoW build 12.1.0.69587).
Regenerate after patches by re-parsing that file — same workflow as the
season seed in upgrade_rules.py.
"""
import json
from functools import lru_cache
from pathlib import Path

SEED = Path(__file__).resolve().parents[2] / "docs" / "embellishments.json"


@lru_cache(maxsize=1)
def load_embellishments(path: str = str(SEED)) -> dict[int, dict]:
    """bonus_id -> {"name": str, "spell_id": int}."""
    data = json.loads(Path(path).read_text())
    return {int(b): v for b, v in data["embellishments"].items()}


def embellishments_for(bonus_ids: list[int] | None) -> list[dict]:
    """Embellishments present on an item from its Armory bonus_list."""
    emb = load_embellishments()
    return [emb[b] for b in (bonus_ids or []) if b in emb]

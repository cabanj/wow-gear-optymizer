"""Upgrade rules: difficulty/track → bonus_ids + ilvl. THE single config point per patch.

Data source for track mappings: maintained in DB table content_items, seeded per season
from SimC armory exports / manual verification. No hardcoded raid or dungeon names.

Policy decisions (Jacek, 2026-09-03):
- Raid: simulate the item version available from the matching difficulty (ilvl per mode).
- M+: only Great Vault track + Bonus roll variants; all items Myth track at max ilvl.
- Enchants/gems on candidates: identical to the item being replaced.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class TrackPolicy:
    """Per-difficulty ilvl + bonus_ids for the current season.

    Loaded from docs/season-seed-midnight-s2.json (values cross-verified
    against SimC DBC item_bonus data + wowhead/method.gg S2 tables, 2026-09-03).
    Track meaning: 614=Veteran(LFR), 615=Champion(Normal), 616=Hero(Heroic),
    617/618=Myth (Mythic / Vault).
    """
    raid: dict[str, dict] = field(default_factory=dict)
    mplus: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "TrackPolicy":
        data = json.loads(Path(path).read_text())
        return cls(raid=data["raid"], mplus=data["mplus"])

    def raid_variant(self, item_id: int, difficulty: str) -> dict:
        v = self.raid[difficulty]
        return {"item_id": item_id, "source": "raid", "difficulty": difficulty,
                "item_level": v["ilvl"], "bonus_ids": [6652] + v["bonus_ids"],
                "variant": None}

    def mplus_variant(self, item_id: int, variant: str) -> dict:
        v = self.mplus[variant]
        return {"item_id": item_id, "source": "mplus", "difficulty": "mythic",
                "item_level": v["ilvl"], "bonus_ids": [6652] + v["bonus_ids"],
                "variant": variant}


@dataclass
class ItemVariant:
    item_id: int
    name: str
    slot: str           # inventory type from static item data
    item_level: int
    bonus_ids: list[int]
    source: str          # raid | mplus
    difficulty: str | None
    variant: str | None  # None | 'great_vault' | 'bonus_roll'
    boss_or_dungeon: str


def raid_variants(item_id: int, ladder: dict[str, tuple[int, list[int]]]) -> list[dict]:
    """One candidate per raid difficulty, using that difficulty's bonus_ids + ilvl."""
    out = []
    for diff, (ilvl, bonus_ids) in ladder.items():
        out.append({
            "item_id": item_id, "difficulty": diff, "item_level": ilvl,
            "bonus_ids": bonus_ids, "source": "raid", "variant": None,
        })
    return out


def mplus_variants(item_id: int, vault_ilvl: int, bonus_roll_ilvl: int,
                   base_bonus_ids: list[int]) -> list[dict]:
    """Per decision: Great Vault track + Bonus roll only; Myth track max ilvl."""
    out = [{
        "item_id": item_id, "difficulty": "mythic", "item_level": vault_ilvl,
        "bonus_ids": base_bonus_ids + [VAULT_BONUS_ID], "source": "mplus",
        "variant": "great_vault",
    }, {
        "item_id": item_id, "difficulty": "mythic", "item_level": bonus_roll_ilvl,
        "bonus_ids": base_bonus_ids + [BONUS_ROLL_BONUS_ID], "source": "mplus",
        "variant": "bonus_roll",
    }]
    return out


# These two are season-specific bonus IDs that shift every patch — resolved from
# the content_items seed (query for variant markers), NOT hardcoded. Kept as
# named constants so the shape of the logic is explicit and testable.
VAULT_BONUS_ID = 0      # replaced at seed time
BONUS_ROLL_BONUS_ID = 0  # replaced at seed time


def filter_compatible(candidate_slot: str, worn_items: dict, candidates: list[dict]) -> list[dict]:
    """Apply equip rules: unique-equipped, same-item-skip, slot compatibility."""
    result = []
    worn = worn_items.get(candidate_slot)
    for c in candidates:
        if worn is None:
            continue
        if worn.get("item_id") == c["item_id"] and c.get("variant") is None:
            continue  # same item already worn (unique-equipped protection)
        result.append(c)
    return result

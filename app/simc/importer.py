"""Parser for /simc addon output (manual import, precise snapshot)."""
import re


def parse_simc_addon(text: str) -> dict | None:
    """Parse the simc addon export. Returns None on invalid input.

    Expects lines like: `head=,bonus_id=..` / `trinket1=...,id=251199,...`
    plus optional talents/spec/level lines.
    """
    if not text or "spec=" not in text:
        return None
    gear: dict[str, dict] = {}
    scalars: dict[str, str] = {}
    slot_re = re.compile(
        r"^(head|shoulder|chest|back|wrist|hands|waist|legs|feet|neck|shoulder|"
        r"finger1|finger2|trinket1|trinket2|main_hand|off_hand|tabard|shirt)=(.*)$"
    )
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = slot_re.match(line)
        if m:
            slot, val = m.group(1), m.group(2)
            fields = {}
            for kv in val.split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    fields[k] = v
                elif kv:
                    fields.setdefault("name", kv)
            gear[slot] = {
                "name": fields.get("name"),
                "item_id": int(fields["id"]) if fields.get("id") else None,
                "bonus_ids": [int(b) for b in fields.get("bonus_id", "").split("/") if b],
                "gem_ids": [g for g in fields.get("gems", "").split("/") if g],
                "enchant": fields.get("enchant"),
                "ilevel": int(fields["ilevel"]) if fields.get("ilevel") else None,
            }
        elif "=" in line and not line.startswith(("profiles", "copy", "armory")):
            k, v = line.split("=", 1)
            scalars[k] = v

    if not gear or not scalars.get("spec"):
        return None
    # average ilvl from gear
    ilvls = [g["ilevel"] for g in gear.values() if g["ilevel"]]
    scalars["item_level"] = round(sum(ilvls) / len(ilvls), 1) if ilvls else None
    scalars["gear"] = gear
    return scalars

"""Scale Blizzard effect descriptions to item level.

Blizzard texts carry base numbers ("grant you 33 Critical Strike for 12 sec").
Scaled values come from the spell resolver (api_cache spellq:{id}:{ilvl}).
"""
import re

RATING_LABELS = {"crit": "Critical Strike", "haste": "Haste", "mastery": "Mastery",
                 "vers": "Versatility", "versatility": "Versatility",
                 "avoid": "Avoidance", "avoidance": "Avoidance", "leech": "Leech",
                 "speed": "Speed"}


def scale_description(desc: str, value: float | None, duration: str | None,
                      rating: str | None, value2: float | None = None) -> str:
    """Replace the base value before the rated stat and the trailing duration.

    value2 covers two-part texts ("gain X ... reduced by Y").
    """
    out = desc or ""
    scaled = False
    if value is not None:
        new = f"{value:.0f}"
        label = RATING_LABELS.get((rating or "").lower()) if rating else None
        if label:
            out2 = re.sub(r"[\d,]+(?=\s+" + re.escape(label) + r")",
                          new, out, count=1)
            scaled = out2 != out
            out = out2
        if not scaled:
            # "gaining/grant you 513 of a random secondary stat" — no stat name
            out2 = re.sub(r"((?:gaining|grant you)\s+)[\d,]+(\s+of a random secondary stat)",
                          r"\g<1>" + new + r"\g<2>", out, count=1)
            scaled = out2 != out
            out = out2
    if scaled and value2 is not None:
        new2 = f"{value2:.0f}"
        # "... and 89 of a random tertiary stat" -> value2
        out3 = re.sub(r"([\s])[\d,]+(\s+of a random tertiary stat)",
                      r"\g<1>" + new2 + r"\g<2>", out, count=1)
        if out3 == out:
            # "... reduced by 73 ..." -> value2
            out3 = re.sub(r"(reduced by\s+)[\d,]+", r"\g<1>" + new2,
                          out, count=1)
        out = out3
    if duration:
        secs = re.sub(r"\s*seconds?\s*$", "", duration).strip()
        if secs.isdigit():
            out = re.sub(r"for [\d,]+ sec", f"for {secs} sec", out, count=1)
    return out

"""Equipment mix detail.

equipment_monthly: claimed Russian losses per month for classes the main
charts leave out: ground robots (reported since 2026-05-03), cruise missiles,
special equipment, air defense and rocket launchers. UA MoD claims.

oryx_tank_age: visually confirmed Russian tank losses by the decade the
model was designed or last modernised, from the Oryx snapshot of
2023-02-05. Old, but it shows how far down its stocks Russia had reached.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .losses import ORYX_AS_OF, ua_mod_daily_deltas

DETAIL_CLASSES = ["ugv", "cruise_missile", "special_equipment", "air_defense", "mrl"]

# Base design year by model family, used when the name has no "Obr. YYYY" (model-year) tag
TANK_FAMILIES = [
    (r"^T-55", 1958), (r"^T-62", 1961), (r"^T-64", 1966), (r"^T-72B3", 2010), (r"^T-72B", 1985),
    (r"^T-72A", 1979), (r"^T-72", 1973), (r"^T-80BVM", 2017), (r"^T-80U", 1985), (r"^T-80BV", 1985),
    (r"^T-80", 1976), (r"^T-90M", 2020), (r"^T-90A", 2004), (r"^T-90", 1992),
]


def equipment_monthly(records: list[dict]) -> list[dict]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for day, cls, n in ua_mod_daily_deltas(records):
        if cls in DETAIL_CLASSES:
            counts[day[:7]][cls] += n
    return [{"month": m, **{c: max(counts[m][c], 0) for c in DETAIL_CLASSES}} for m in sorted(counts)]


def tank_design_year(model: str) -> int | None:
    m = re.search(r"Obr\.\s*(\d{4})", model)
    if m:
        return int(m.group(1))
    for pat, year in TANK_FAMILIES:
        if re.search(pat, model.strip()):
            return year
    return None


def oryx_tank_age(oryx_records: list[dict]) -> list[dict]:
    by_decade: dict[str, int] = defaultdict(int)
    for r in oryx_records:
        if r.get("equipment_oryx") != "Tanks":
            continue
        year = tank_design_year(r.get("model", ""))
        key = f"{year // 10 * 10}s" if year else "Unknown model"
        by_decade[key] += int(r.get("losses_total", 0))
    order = sorted(k for k in by_decade if k != "Unknown model") + (["Unknown model"] if "Unknown model" in by_decade else [])
    total = sum(by_decade.values())
    return [{"design_decade": k, "tanks_lost": by_decade[k], "share": round(by_decade[k] / total, 3), "as_of": ORYX_AS_OF}
            for k in order]

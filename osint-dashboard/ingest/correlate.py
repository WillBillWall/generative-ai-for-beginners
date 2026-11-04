"""Tactics vs territory: what moved with the front line, and who held the advantage.

Joins DeepStateMap's monthly territory change with UA MoD claimed Russian losses
(equipment and personnel) and the tactic reports. Everything here describes
co-movement, not cause: 28 months is a small sample, the months are not
independent, loss figures are one side's claims, and tactic reports overlap.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import numpy as np

from .common import sides_of
from .losses import MIRROR, fetch_json

PERSONNEL_URL = f"{MIRROR}/russia_losses_personnel.json"
LOSS_SERIES = {
    "personnel_per_day": "Russian personnel",
    "tank_per_day": "Tanks",
    "afv_per_day": "Armored vehicles",
    "artillery_per_day": "Artillery",
    "uav_per_day": "Drones",
    "vehicles_per_day": "Logistics vehicles",
}
# Pace bands for advantage periods, in km² of net Russian gain per day (3-month average).
BANDS = [(8.0, "Russia advancing fast"), (3.0, "Russia advancing slowly"), (0.0, "Front stalled"),
         (-math.inf, "Ukraine gaining")]


def personnel_monthly(records: list[dict]) -> dict[str, float]:
    """Claimed Russian personnel losses per day, by month, from daily cumulative totals."""
    records = sorted(records, key=lambda r: r["date"])
    totals: dict[str, int] = defaultdict(int)
    days: dict[str, set] = defaultdict(set)
    prev = None
    for r in records:
        v = r.get("personnel")
        if not isinstance(v, (int, float)):
            continue
        if prev is not None:
            totals[r["date"][:7]] += int(v) - prev
            days[r["date"][:7]].add(r["date"])
        prev = int(v)
    return {m: totals[m] / len(days[m]) for m in totals if days[m]}


def _ranks(x: np.ndarray) -> np.ndarray:
    order = x.argsort(kind="mergesort")
    ranks = np.empty(len(x))
    ranks[order] = np.arange(len(x), dtype=float)
    for v in np.unique(x):                      # average ranks for ties
        idx = np.where(x == v)[0]
        ranks[idx] = ranks[idx].mean()
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    a_arr, b_arr = np.asarray(a, float), np.asarray(b, float)
    if len(a_arr) < 6 or a_arr.std() == 0 or b_arr.std() == 0:
        return None
    return float(np.corrcoef(_ranks(a_arr), _ranks(b_arr))[0, 1])


def joined(territory_monthly: list[dict], monthly: list[dict], personnel: dict[str, float]) -> list[dict]:
    loss = {r["month"]: r for r in monthly if r["complete"]}
    out = []
    for t in territory_monthly:
        m = t["month"]
        if not t["complete"] or m not in loss or m not in personnel:
            continue
        row = {"month": m, "km2_per_day": t["km2_per_day"], "personnel_per_day": round(personnel[m], 1)}
        for k in LOSS_SERIES:
            if k != "personnel_per_day":
                row[k] = loss[m][k]
        out.append(row)
    # cost of advance, 3-month rolling sums so a single quiet month cannot divide by ~0
    for i, row in enumerate(out):
        win = out[max(0, i - 2): i + 1]
        gain = sum(r["km2_per_day"] for r in win)
        row["km2_per_day_3m"] = round(gain / len(win), 2)
        if gain > 0.5:
            row["personnel_per_km2_3m"] = round(sum(r["personnel_per_day"] for r in win) / gain, 1)
            row["armor_per_km2_3m"] = round(sum(r["tank_per_day"] + r["afv_per_day"] for r in win) / gain, 3)
        else:
            row["personnel_per_km2_3m"] = None
            row["armor_per_km2_3m"] = None
    return out


def correlations(rows: list[dict]) -> list[dict]:
    """Spearman correlation of monthly *changes* (this month minus last).

    Levels are misleading here: drone, artillery and logistics losses climb
    steadily while gains fall, so any two such series correlate on trend alone.
    Changes ask a sharper question: in months when this loss rate went up, did
    gains go up or down? `rho_levels` is kept only to show the trend effect.
    """
    gains = [r["km2_per_day"] for r in rows]
    dg = [b - a for a, b in zip(gains, gains[1:])]
    out = []
    for key, label in LOSS_SERIES.items():
        vals = [r[key] for r in rows]
        dv = [b - a for a, b in zip(vals, vals[1:])]
        rec = {"series": key, "label": label, "n_months": len(dv)}
        lev = spearman(vals, gains)
        rec["rho_levels"] = round(lev, 2) if lev is not None else None
        for lag in (0, 1):           # loss change leads the gain change by `lag` months
            a = dv[: len(dv) - lag] if lag else dv
            rho = spearman(a, dg[lag:])
            rec[f"rho_change_lag{lag}"] = round(rho, 2) if rho is not None else None
        out.append(rec)
    return out


def _month_add(m: str, k: int) -> str:
    y, mo = int(m[:4]), int(m[5:7]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


def turning_points(observations: list[dict]) -> list[dict]:
    """Reports that mark a change in a row: its first report, a step up in stage, or a counter.

    RUSI papers are left out: they review the previous year, so their dates are
    not when the tactic changed.
    """
    rank = {"emerging": 0, "spreading": 1, "widespread": 2, "fading": 3, "resurgent": 1}
    last: dict[tuple[str, str], str] = {}
    out = []
    for o in sorted(observations, key=lambda o: o["date"]):
        if o["source_org"] == "RUSI":
            continue
        for side in sides_of(o):
            key = (o["tactic_subtype"], side)
            prev = last.get(key)
            if prev is None or rank.get(o["stage"], 0) > rank.get(prev, 0) or o.get("counter_reported") == "yes":
                out.append({**o, "lane": side})
            last[key] = o["stage"]
    return out


def before_after(rows: list[dict], observations: list[dict], window: int = 3) -> list[dict]:
    """Average km²/day in the `window` months before vs after each turning-point report, per side row."""
    pace = {r["month"]: r["km2_per_day"] for r in rows}
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    meta: dict[tuple[str, str], dict] = {}
    for o in turning_points(observations):
        m = o["date"][:7]
        before = [pace.get(_month_add(m, -k)) for k in range(1, window + 1)]
        after = [pace.get(_month_add(m, k)) for k in range(1, window + 1)]
        if None in before or None in after:
            continue
        delta = sum(after) / window - sum(before) / window
        winter = sum(1 for k in range(1, window + 1) if _month_add(m, k)[5:7] in ("12", "01", "02"))
        key = (o["tactic_subtype"], o["lane"])
        groups[key].append(delta)
        meta.setdefault(key, {"subtype_label": o["subtype_label"], "subtype_phrase": o.get("subtype_phrase", ""),
                              "category_label": o["category_label"], "dates": [], "what": [], "winter": 0})
        meta[key]["winter"] = max(meta[key]["winter"], winter)
        meta[key]["dates"].append(o["date"])
        meta[key]["what"].append("counter reported" if o.get("counter_reported") == "yes" else o["stage"])
    out = []
    for (sub, side), deltas in groups.items():
        mt = meta[(sub, side)]
        out.append({"row_key": f"{sub}|{side}", "tactic_subtype": sub, "side": side,
                    "subtype_label": mt["subtype_label"], "subtype_phrase": mt["subtype_phrase"],
                    "category_label": mt["category_label"], "reports": len(deltas),
                    "first_report": min(mt["dates"]), "last_report": max(mt["dates"]),
                    "change_reported": "; ".join(f"{d[:7]} {w}" for d, w in zip(mt["dates"], mt["what"])),
                    "mean_change_km2_per_day": round(sum(deltas) / len(deltas), 1),
                    # winter months in the 'after' window; winter slows advances regardless of tactics
                    "winter_months_after": mt["winter"]})
    return sorted(out, key=lambda r: r["mean_change_km2_per_day"])


def _edge_text(o: dict) -> str:
    what = ("countered" if o.get("counter_reported") == "yes"
            else "first seen" if o["stage"] == "emerging" else o["stage"])
    return f"{o.get('subtype_phrase') or o['subtype_label']} {what} ({o['date'][:7]})"


def advantage_periods(rows: list[dict], observations: list[dict] | None = None,
                      lead: int = 3, lag: int = 1) -> list[dict]:
    """Group consecutive months by pace band (3-month average km²/day).

    For each period, `ru_changes` / `ua_changes` list each side's turning-point
    reports from `lead` months before the period started to `lag` months after:
    the tactical changes that line up in time with the shift. Timing only.
    """
    def band(v: float) -> str:
        return next(name for lo, name in BANDS if v >= lo)
    periods: list[dict] = []
    for r in rows:
        b = band(r["km2_per_day_3m"])
        if periods and periods[-1]["band"] == b:
            periods[-1]["rows"].append(r)
        else:
            periods.append({"band": b, "rows": [r]})
    tps = turning_points(observations or [])
    out = []
    for p in periods:
        rs = p["rows"]
        costs = [r["personnel_per_km2_3m"] for r in rs if r["personnel_per_km2_3m"] is not None]
        lo, hi = _month_add(rs[0]["month"], -lead), _month_add(rs[0]["month"], lag)
        near = [o for o in tps if lo <= o["date"][:7] <= hi]
        out.append({"band": p["band"], "from_month": rs[0]["month"], "to_month": rs[-1]["month"], "months": len(rs),
                    "km2_per_day": round(sum(r["km2_per_day"] for r in rs) / len(rs), 1),
                    "personnel_per_km2": round(sum(costs) / len(costs), 1) if costs else None,
                    "ru_changes": "; ".join(_edge_text(o) for o in near if o["lane"] == "RU"),
                    "ua_changes": "; ".join(_edge_text(o) for o in near if o["lane"] == "UA")})
    return out


def run(territory_monthly: list[dict], monthly: list[dict], observations: list[dict], refresh: bool = False) -> dict[str, list[dict]]:
    personnel = personnel_monthly(fetch_json(PERSONNEL_URL, "ua_mod_personnel.json", refresh))
    rows = joined(territory_monthly, monthly, personnel)
    return {
        "territory_vs_losses.csv": rows,
        "loss_correlations.csv": correlations(rows),
        "tactic_before_after.csv": before_after(rows, observations),
        "advantage_periods.csv": advantage_periods(rows, observations),
    }

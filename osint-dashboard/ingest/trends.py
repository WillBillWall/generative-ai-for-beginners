"""Trend analysis over the normalized data.

monthly_rates      per-day loss rates by month, plus fires-vs-maneuver ratios
trend_rates        log-linear growth/decline per class over two 12-month windows
shift_points       months where a class's trend changed (binary segmentation)
adaptation         per tactic, months from first observation to spread / counter

All loss figures are UA MoD claims of Russian losses: they describe the trend
in what Ukraine reports destroying, not audited counts.
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date

import numpy as np

from .common import WAR_START, sides_of
from .losses import ua_mod_daily_deltas

RATE_CLASSES = ["tank", "afv", "artillery", "mrl", "air_defense", "uav", "vehicles", "ugv"]
TREND_CLASSES = ["tank", "afv", "artillery", "mrl", "air_defense", "uav", "vehicles"]
SHIFT_CLASSES = ["tank", "afv", "artillery", "uav", "vehicles"]
SPREAD_ORDER = {"emerging": 0, "spreading": 1, "widespread": 2}
DAYS_PER_MONTH = 30.44
INDEX_CLASSES = ["tank", "afv", "artillery", "vehicles", "uav"]
BASELINE_MONTHS = ("2022-04", "2022-05", "2022-06")  # first full quarter of the war


def _month_days(month: str, first: date, last: date) -> int:
    y, m = int(month[:4]), int(month[5:7])
    start = max(date(y, m, 1), first)
    end = min(date(y, m, calendar.monthrange(y, m)[1]), last)
    return (end - start).days + 1


def _ratio(num: float, den: float) -> float | None:
    return round(num / den, 2) if den else None


def monthly_rates(records: list[dict]) -> list[dict]:
    deltas = ua_mod_daily_deltas(records)
    last = date.fromisoformat(max(d for d, _, _ in deltas))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for day, cls, n in deltas:
        counts[day[:7]][cls] += n
    months = sorted(counts)
    base_days = sum(_month_days(m, WAR_START, last) for m in BASELINE_MONTHS)
    baseline = {cls: sum(counts[m][cls] for m in BASELINE_MONTHS) / base_days for cls in INDEX_CLASSES}
    rows = []
    for i, mo in enumerate(months):
        days = _month_days(mo, WAR_START, last)
        full = days == calendar.monthrange(int(mo[:4]), int(mo[5:7]))[1]
        c = counts[mo]
        row = {"month": mo, "days": days, "complete": full}
        for cls in RATE_CLASSES:
            row[f"{cls}_per_day"] = round(max(c[cls], 0) / days, 2)
        # 3-month rolling ratios from summed counts (not a mean of ratios)
        window = [counts[m] for m in months[max(0, i - 2): i + 1]]
        s = {cls: sum(w[cls] for w in window) for cls in RATE_CLASSES}
        armor = s["tank"] + s["afv"]
        days3 = sum(_month_days(m, WAR_START, last) for m in months[max(0, i - 2): i + 1])
        for cls in INDEX_CLASSES:
            row[f"{cls}_index_3m"] = _ratio(s[cls] / days3, baseline[cls]) if baseline.get(cls) else None
        row["fires_per_armor_3m"] = _ratio(s["artillery"] + s["mrl"], armor)
        row["vehicles_per_armor_3m"] = _ratio(s["vehicles"], armor)
        row["drones_per_armor_3m"] = _ratio(s["uav"], armor)
        rows.append(row)
    return rows


def log_trend(rates: list[float]) -> dict:
    """Fit ln(rate) = a + b*t over consecutive months; zero months are dropped."""
    t = np.array([i for i, r in enumerate(rates) if r > 0], dtype=float)
    y = np.log([r for r in rates if r > 0])
    if len(t) < 6:
        return {"monthly_growth": None, "per_quarter_pct": None, "doubling_months": None, "r2": None}
    b, a = np.polyfit(t, y, 1)
    resid = y - (a + b * t)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - float((resid ** 2).sum()) / ss_tot if ss_tot else 0.0
    return {
        "monthly_growth": float(b),
        "per_quarter_pct": round((math.exp(3 * b) - 1) * 100, 1),
        # positive: doubling time; negative: halving time (in months)
        "doubling_months": round(math.log(2) / b, 1) if abs(b) > 1e-9 else None,
        "r2": round(r2, 2),
    }


def trend_rates(monthly: list[dict]) -> list[dict]:
    full = [r for r in monthly if r["complete"]]
    windows = {"last_12m": full[-12:], "prior_12m": full[-24:-12]}
    rows = []
    for cls in TREND_CLASSES:
        key = f"{cls}_per_day"
        last3 = full[-3:]
        year_ago = full[-15:-12]
        now = sum(r[key] * r["days"] for r in last3) / sum(r["days"] for r in last3)
        then = sum(r[key] * r["days"] for r in year_ago) / sum(r["days"] for r in year_ago)
        yoy = round((now / then - 1) * 100, 1) if then else None
        for name, win in windows.items():
            fit = log_trend([r[key] for r in win])
            rows.append({
                "equipment_class": cls, "window": name,
                "from_month": win[0]["month"], "to_month": win[-1]["month"],
                "per_quarter_pct": fit["per_quarter_pct"],
                "doubling_months": fit["doubling_months"], "r2": fit["r2"],
                "yoy_pct": yoy if name == "last_12m" else None,
                "latest_3m_per_day": round(now, 2) if name == "last_12m" else None,
            })
    return rows


def _sse(t: np.ndarray, y: np.ndarray) -> float:
    if len(t) < 2:
        return 0.0
    b, a = np.polyfit(t, y, 1)
    return float(((y - (a + b * t)) ** 2).sum())


def segment(y: list[float], *, min_len: int = 6, max_breaks: int = 3, min_gain: float = 0.25) -> list[int]:
    """Binary segmentation with a separate straight line per segment.

    A split is kept when it removes at least `min_gain` of the segment's
    squared error and leaves both sides at least `min_len` long. Returns the
    sorted indexes where new segments start.
    """
    y_arr = np.asarray(y, dtype=float)
    t_all = np.arange(len(y_arr), dtype=float)
    segments, breaks = [(0, len(y_arr))], []
    while len(breaks) < max_breaks:
        best = None
        for s, e in segments:
            base = _sse(t_all[s:e], y_arr[s:e])
            if base < 1e-9:  # already a perfect fit; float noise is not a trend change
                continue
            for k in range(s + min_len, e - min_len + 1):
                gain = (base - _sse(t_all[s:k], y_arr[s:k]) - _sse(t_all[k:e], y_arr[k:e])) / base
                if gain >= min_gain and (best is None or gain > best[0]):
                    best = (gain, s, k, e)
        if best is None:
            break
        _, s, k, e = best
        segments.remove((s, e))
        segments += [(s, k), (k, e)]
        breaks.append(k)
    return sorted(breaks)


def _months_between(a: str, b: str) -> float:
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days / DAYS_PER_MONTH


def shift_points(monthly: list[dict], observations: list[dict], window_months: float = 3.0) -> list[dict]:
    full = [r for r in monthly if r["complete"]]
    rows = []
    for cls in SHIFT_CLASSES:
        series = [(r["month"], r[f"{cls}_per_day"]) for r in full if r[f"{cls}_per_day"] > 0]
        y = [math.log(v) for _, v in series]
        for k in segment(y):
            before, after = y[max(0, k - 6):k], y[k:k + 6]
            slope_b = np.polyfit(range(len(before)), before, 1)[0]
            slope_a = np.polyfit(range(len(after)), after, 1)[0]
            month = series[k][0]
            near = [o for o in observations
                    if abs(_months_between(f"{month}-15", o["date"])) <= window_months]
            rows.append({
                "equipment_class": cls, "month": month,
                "rate_before": round(series[k - 1][1], 2), "rate_after": round(series[k][1], 2),
                "trend_before_pct_month": round((math.exp(slope_b) - 1) * 100, 1),
                "trend_after_pct_month": round((math.exp(slope_a) - 1) * 100, 1),
                "nearby_events": len(near),
                "nearby": "; ".join(f"{o['date'][:7]} {o['subtype_label']} ({o['stage']})" for o in near[:4]),
            })
    return rows


def adaptation(observations: list[dict]) -> list[dict]:
    """Per row (tactic + side): months from first report to spreading further, and to a counter.

    spread: first later report at a higher usage stage (emerging < spreading < widespread).
    counter: first later report with counter_reported = yes, or the first report itself if it
    already says so (then 0 months is not meaningful and is left blank).
    """
    by_row: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for o in observations:
        for side in sides_of(o):
            by_row[(o["tactic_subtype"], side)].append(o)
    rows = []
    for (sub, side), obs in by_row.items():
        obs = sorted(obs, key=lambda o: o["date"])
        first = obs[0]
        rank0 = SPREAD_ORDER.get(first["stage"], -1)
        spread = next((o for o in obs[1:] if SPREAD_ORDER.get(o["stage"], -1) > rank0), None) if rank0 >= 0 else None
        counter = next((o for o in obs[1:] if o.get("counter_reported") == "yes"), None)
        rows.append({
            "row_key": f"{sub}|{side}", "tactic_subtype": sub, "side": side,
            "subtype_label": first["subtype_label"], "category_label": first["category_label"],
            "observations": len(obs), "first_seen": first["date"], "first_stage": first["stage"],
            "first_year": int(first["date"][:4]),
            "spread_stage": spread["stage"] if spread else "",
            "months_to_spread": round(_months_between(first["date"], spread["date"]), 1) if spread else None,
            "months_to_counter": round(_months_between(first["date"], counter["date"]), 1) if counter else None,
            "first_summary": first.get("summary", ""),
            "spread_date": spread["date"] if spread else "",
            "spread_summary": spread.get("summary", "") if spread else "",
            "counter_date": counter["date"] if counter else "",
            "counter_summary": counter.get("summary", "") if counter else "",
        })
    return sorted(rows, key=lambda r: r["first_seen"])


def adaptation_by_year(rows: list[dict]) -> list[dict]:
    out = []
    for year in sorted({r["first_year"] for r in rows}):
        vals = [r["months_to_spread"] for r in rows if r["first_year"] == year and r["months_to_spread"] is not None]
        if vals:
            out.append({"first_year": year, "tactics": len(vals),
                        "median_months_to_spread": round(float(np.median(vals)), 1)})
    return out

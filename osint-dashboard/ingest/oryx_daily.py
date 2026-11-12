"""Oryx visually confirmed equipment losses for both sides, month by month.

Source: daily cumulative snapshots of the Oryx loss lists, kept in the GitHub repo
leedrake5/Russia-Ukraine (MIT licence; underlying data by Oryx). One CSV per day from
2022-02-24: data/byType/YYYY-MM-DD.csv, about 50 rows, with the columns country,
equipment_type, destroyed, abandoned, captured, damaged, type_total, row_id, Date.
Method: visually_confirmed.

We download the snapshot of the first available day (1st to 5th) of every month, the
war-start day and the latest available day, and difference consecutive snapshots.

Caveats
- Dates are when Oryx documented a loss, not when it happened; backlogs make months lumpy.
- Only losses with photo or video evidence count, so both sides are undercounted, and
  Ukrainian losses probably more so (less footage is published of them).
- Cumulative counts sometimes fall when Oryx removes duplicates. A fall counts as zero
  losses in that month; the cumulative column keeps the true figure.
- Each file has an "All Types" total per side and, from 2022-08, a free-text subtotal row
  ("Losses of Armoured Combat Vehicles [...] - 14203, of which: ..."). Both are skipped;
  "all" in the ratio table is the sum of the classes.
- Type names changed over time (see TYPE_CLASS) and some carry stray line breaks.
- If no snapshot exists for the 1st to 5th of a month, the losses of that month are
  counted in the month before it.

Outputs
- oryx_monthly.csv: per month, side and equipment class: cumulative total and losses documented
- oryx_ratio_monthly.csv: per month, Russian losses per Ukrainian loss (tanks, AFVs, all)
- oryx_latest.csv: latest cumulative totals by side, class and status
"""
from __future__ import annotations

import csv
import io
import time
from collections import defaultdict
from datetime import date, timedelta

import requests

from .common import RAW, USER_AGENT, WAR_START
from .losses import ORYX_CATEGORIES

URL = "https://raw.githubusercontent.com/leedrake5/Russia-Ukraine/master/data/byType/{day}.csv"
SOURCE_URL = "https://github.com/leedrake5/Russia-Ukraine"
CACHE = RAW / "oryx_daily"
FIRST_MONTH = (2022, 3)
SIDES = {"russia": "RU", "ukraine": "UA"}
STATUSES = ("destroyed", "damaged", "abandoned", "captured")

# Oryx type name (lower case, single spaces) -> our equipment classes (taxonomy.yaml).
# Starts from the map for the older Oryx format in ingest/losses.py; the entries below
# are every other name seen in the month-start snapshots 2022-02 to 2026-11.
TYPE_CLASS = {name.lower(): cls for name, cls in ORYX_CATEGORIES.items()}
TYPE_CLASS.update({
    "armoured recovery vehicles": "special_equipment",
    "engineering vehicles": "special_equipment",
    "communications stations": "command_comms",
    "communications vehicles": "command_comms",
    "command posts": "command_comms",
    "heavy mortars": "artillery",
    "mortars": "artillery",
    "self-propelled mortars": "artillery",
    "anti-tank guided missiles": "other",
    "man-portable air defence systems": "air_defense",
    "artillery support vehicles and equipment": "artillery",
    "artillery and missile support vehicles and equipment": "artillery",
    "rocket and missile artillery": "mrl",
    "radars and communications equipment": "ew_radar",
    "combat unmanned aerial vehicles": "uav",
    "logistics trains": "vehicles",
    "trucks and similar vehicles": "vehicles",
    "trucks, vehicles, and jeeps": "vehicles",
    "trucks, vehicles and jeeps": "vehicles",
})


def clean_type(type_name: str | None) -> str:
    """Lower case with single spaces: the files contain stray line breaks and case changes."""
    return " ".join(str(type_name or "").split()).lower()


def is_total(type_name: str | None) -> bool:
    """True for the 'All Types' row and the free-text armoured-vehicle subtotal row."""
    name = clean_type(type_name)
    return not name or name.startswith("all types") or name.startswith("losses of") or "of which" in name


def equipment_class(type_name: str | None) -> str | None:
    """Oryx type name -> equipment class; None for total and summary rows; 'other' if unknown."""
    if is_total(type_name):
        return None
    return TYPE_CLASS.get(clean_type(type_name), "other")


def parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def _num(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _side(row: dict) -> str | None:
    return SIDES.get(str(row.get("country") or "").strip().lower())


def _download(session: requests.Session, day: str, pause: float) -> str | None:
    """One snapshot as text, or None when that day has no file (404)."""
    resp = session.get(URL.format(day=day), timeout=30)
    time.sleep(pause)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text if "equipment_type" in resp.text[:300] else None


def month_list(today: date) -> list[tuple[int, int]]:
    out, (y, m) = [], FIRST_MONTH
    while (y, m) <= (today.year, today.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch_month_starts(today: date | None = None, session: requests.Session | None = None,
                       pause: float = 0.3) -> dict[str, list[dict]]:
    """Snapshots for the war-start day, the first available day (1st to 5th) of every month
    from 2022-03 and the latest available day (today back to today-6).

    Cached files are never downloaded again, except the latest day, which is always probed.
    About 60 requests on a cold cache.
    """
    today = today or date.today()
    session = session or requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    CACHE.mkdir(parents=True, exist_ok=True)
    snapshots: dict[str, list[dict]] = {}

    def get(day: date, force: bool = False) -> bool:
        key, path = day.isoformat(), CACHE / f"{day.isoformat()}.csv"
        if force or not path.exists():
            text = _download(session, key, pause)
            if text is not None:
                path.write_text(text)
        if not path.exists():
            return False
        snapshots[key] = parse_csv(path.read_text())
        return True

    get(WAR_START)
    for y, m in month_list(today):
        days = [date(y, m, d) for d in range(1, 6) if date(y, m, d) <= today]
        cached = [d for d in days if (CACHE / f"{d.isoformat()}.csv").exists()]
        for d in cached[:1] or days:
            if get(d):
                break
    for back in range(7):
        if get(today - timedelta(days=back), force=True):
            break
    return dict(sorted(snapshots.items()))


def load_cached() -> dict[str, list[dict]]:
    """Every cached snapshot, without touching the network."""
    return {p.stem: parse_csv(p.read_text()) for p in sorted(CACHE.glob("????-??-??.csv"))}


def class_totals(rows: list[dict], field: str = "type_total") -> dict[tuple[str, str], int]:
    """One snapshot -> {(side, equipment class): count}, total and summary rows left out."""
    out: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        side, cls = _side(row), equipment_class(row.get("equipment_type"))
        if side and cls:
            out[(side, cls)] += _num(row.get(field))
    return dict(out)


def period_snapshots(snapshots: dict[str, list[dict]]) -> list[str]:
    """Dates that bound the periods: the first snapshot of each month, then the latest one."""
    dates = sorted(snapshots)
    firsts: dict[str, str] = {}
    for d in dates:
        firsts.setdefault(d[:7], d)
    bounds = sorted(firsts.values())
    if dates and dates[-1] != bounds[-1]:
        bounds.append(dates[-1])
    return bounds


def monthly(snapshots: dict[str, list[dict]]) -> list[dict]:
    """Cumulative snapshots -> losses documented per month, side and equipment class.

    A month's losses are the next month's first snapshot minus this month's first snapshot
    (for the last month: the latest snapshot minus its first, so that month is partial).
    'cumulative' is the true total at the end of the period. Falls are clamped to zero.
    A class missing from a snapshot counts as zero there.
    """
    bounds = period_snapshots(snapshots)
    totals = {d: class_totals(snapshots[d]) for d in bounds}
    keys = sorted({k for t in totals.values() for k in t})
    out = []
    for start, end in zip(bounds, bounds[1:]):
        for side, cls in keys:
            before, after = totals[start].get((side, cls), 0), totals[end].get((side, cls), 0)
            if not before and not after:
                continue
            out.append({"month": start[:7], "side": side, "equipment_class": cls,
                        "cumulative": after, "lost_in_month": max(after - before, 0)})
    return out


def _ratio(ru: int, ua: int) -> float | None:
    return round(ru / ua, 2) if ua else None


def ratio_monthly(monthly_rows: list[dict]) -> list[dict]:
    """Per month: losses by side for tanks, AFVs, artillery and all classes, and Russian
    losses per Ukrainian loss. The _3m ratio uses sums over this month and the two before
    it (None until three months exist, or when Ukraine lost nothing in them)."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in monthly_rows:
        side = r["side"].lower()
        counts[r["month"]][f"{side}_all"] += r["lost_in_month"]
        if r["equipment_class"] in ("tank", "afv", "artillery"):
            counts[r["month"]][f"{side}_{r['equipment_class']}"] += r["lost_in_month"]
    months = sorted(counts)
    out = []
    for i, m in enumerate(months):
        c = counts[m]
        row = {"month": m}
        for cls in ("tank", "afv", "artillery", "all"):
            row[f"ru_{cls}"], row[f"ua_{cls}"] = c[f"ru_{cls}"], c[f"ua_{cls}"]
        for cls in ("tank", "afv", "all"):
            row[f"ru_per_ua_{cls}"] = _ratio(c[f"ru_{cls}"], c[f"ua_{cls}"])
        window = months[i - 2:i + 1] if i >= 2 else []
        row["ru_per_ua_all_3m"] = _ratio(sum(counts[w]["ru_all"] for w in window),
                                         sum(counts[w]["ua_all"] for w in window))
        out.append(row)
    return out


def latest_totals(snapshots: dict[str, list[dict]]) -> list[dict]:
    """Latest snapshot -> cumulative losses by side, equipment class and status."""
    if not snapshots:
        return []
    as_of = max(snapshots)
    by_field = {f: class_totals(snapshots[as_of], f) for f in STATUSES + ("type_total",)}
    out = []
    for side, cls in sorted(by_field["type_total"]):
        row = {"as_of": as_of, "side": side, "equipment_class": cls}
        for f in STATUSES:
            row[f] = by_field[f].get((side, cls), 0)
        row["total"] = by_field["type_total"][(side, cls)]
        out.append(row)
    return out


def run(refresh: bool = False) -> dict[str, list[dict]]:
    snapshots = {} if refresh else load_cached()
    if not snapshots:
        snapshots = fetch_month_starts()
    rows = monthly(snapshots)
    return {"oryx_monthly.csv": rows,
            "oryx_ratio_monthly.csv": ratio_monthly(rows),
            "oryx_latest.csv": latest_totals(snapshots)}

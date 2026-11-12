"""War-related fires in Ukraine, from The Economist's war-fire model.

Source: github.com/TheEconomist/the-economist-war-fire-model (code MIT, data
CC BY 4.0, cite The Economist). The model takes NASA FIRMS satellite heat
detections in Ukraine and labels a fire "war-related" when fire activity in its
0.1 x 0.1 degree cell on that day is abnormal (under 5% probability in a normal
year) and such excess is sustained nearby, or when it falls in a cell within 10
days of such an event.

We read only the daily summary, output-data/strikes_by_location_and_day.csv
(one row per day from 2022-02-23, newest first, rebuilt several times a day):

- fires_per_day / war_fires_per_day: all detections in Ukraine that day / those
  classified as war-related.
- ..._in_ukraine_held_area / ..._in_russia_held_area: the same split by whether
  the fire lay outside or inside the area ISW assessed as Russian-controlled on
  that date ("Russia-held" strictly means "not assessed as Ukraine-held", so it
  includes claimed and contested ground). The two always sum to the total.
- cloud_cover_in_country / cloud_cover_in_east_of_country: share of the sky
  covered (0-1); the latest days are a forecast.
- *_7dma: centred 7-day mean (3 days either side, so it is shorter at the ends
  and the last 3 days change as new days arrive).
- *_non_cloud_days_7dma: the same mean over only the days in the window with
  eastern cloud cover of 0.5 or less; "NA" when every day was cloudy.

Used here: the three war-fire counts, eastern cloud cover (the measure the
source itself masks on, and where the front is) and war_fires_per_day_7dma.

Caveats: this counts heat the satellites saw, not strikes. Cloud hides fires, so
winters read low and the series is strongly seasonal; compare a month with the
same month a year earlier, not with the month before. Days without detections
are written as 0 by the source, so "no fires" and "no data yet" look the same.
The classifier is strict (misses many war events, sometimes flags farm fires)
and is switched off in extreme heat (4-11 April 2023 per the README).
"""
from __future__ import annotations

import calendar
import csv
import io
from datetime import date, datetime, timezone

from .common import RAW, polite_get

URL = ("https://raw.githubusercontent.com/TheEconomist/the-economist-war-fire-model/"
       "master/output-data/strikes_by_location_and_day.csv")
SOURCE_PAGE = "https://github.com/TheEconomist/the-economist-war-fire-model"
CACHE = RAW / "war_fires_daily.csv"
DAILY_KEEP = 400

COUNTS = {
    "war_fires": "war_fires_per_day",
    "war_fires_ua_held": "war_fires_per_day_in_ukraine_held_area",
    "war_fires_ru_held": "war_fires_per_day_in_russia_held_area",
}
CLOUD = "cloud_cover_in_east_of_country"
AVG_7D = "war_fires_per_day_7dma"
_BLANK = {"", "na", "nan", "null", "none"}


def fetch(refresh: bool = False) -> list[dict]:
    """Rows of the daily summary CSV; downloads only when asked or not yet cached."""
    if refresh or not CACHE.exists():
        text = polite_get(URL, timeout=60).text
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(text)
    else:
        text = CACHE.read_text()
    return list(csv.DictReader(io.StringIO(text)))


def _num(value) -> float | None:
    if value is None or str(value).strip().lower() in _BLANK:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _count(value) -> int | float | None:
    n = _num(value)
    return int(n) if n is not None and n == int(n) else n


def daily(rows: list[dict], today: date | None = None) -> list[dict]:
    """Tidy rows, oldest first. The latest day is dropped while it is still being filled."""
    today = today or datetime.now(timezone.utc).date()
    has_cloud = any(CLOUD in r for r in rows)
    out = []
    for r in sorted(rows, key=lambda r: r.get("date") or ""):
        if not r.get("date"):
            continue
        row = {"date": r["date"][:10]}
        for name, col in COUNTS.items():
            row[name] = _count(r.get(col))
        if has_cloud:
            row["cloud_cover"] = _num(r.get(CLOUD))
        avg = _num(r.get(AVG_7D))
        row["war_fires_7d"] = round(avg, 1) if avg is not None else None
        out.append(row)
    if out and (out[-1]["date"] >= today.isoformat() or any(out[-1][k] is None for k in COUNTS)):
        out.pop()
    return out


def _per_day(rs: list[dict], key: str) -> tuple[float | None, float]:
    vals = [r[key] for r in rs if r.get(key) is not None]
    return (round(sum(vals) / len(vals), 1) if vals else None), sum(vals)


def monthly(daily_rows: list[dict]) -> list[dict]:
    by_month: dict[str, list[dict]] = {}
    for r in daily_rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    out = []
    for month in sorted(by_month):
        rs = by_month[month]
        war, _ = _per_day(rs, "war_fires")
        ua, ua_sum = _per_day(rs, "war_fires_ua_held")
        ru, ru_sum = _per_day(rs, "war_fires_ru_held")
        days_in_month = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
        out.append({
            "month": month, "days": len(rs),
            "complete": len({r["date"] for r in rs}) == days_in_month,
            "war_fires_per_day": war, "ua_held_per_day": ua, "ru_held_per_day": ru,
            # where the detected war fires fall: 1.0 = all on Ukrainian-held ground
            "ua_held_share": round(ua_sum / (ua_sum + ru_sum), 3) if ua_sum + ru_sum > 0 else None,
        })
    return out


def seasonal_index(monthly_rows: list[dict]) -> list[dict]:
    """Each month against the same calendar month a year earlier.

    The change is None unless both months are complete and the earlier one is
    above zero: a part-month against a full one is not like for like.
    """
    by_month = {r["month"]: r for r in monthly_rows}
    out = []
    for r in monthly_rows:
        prev = by_month.get(f"{int(r['month'][:4]) - 1}{r['month'][4:]}")
        now_v = r["war_fires_per_day"]
        prev_v = prev["war_fires_per_day"] if prev else None
        comparable = (prev is not None and r.get("complete") and prev.get("complete")
                      and now_v is not None and prev_v)
        out.append({
            "month": r["month"], "war_fires_per_day": now_v, "same_month_prev_year": prev_v,
            "yoy_pct": round(100 * (now_v - prev_v) / prev_v, 1) if comparable else None,
        })
    return out


def run(refresh: bool = False) -> dict[str, list[dict]]:
    days = daily(fetch(refresh))
    months = monthly(days)
    yoy = {r["month"]: r for r in seasonal_index(months)}
    merged = [{**m, "same_month_prev_year": yoy[m["month"]]["same_month_prev_year"],
               "yoy_pct": yoy[m["month"]]["yoy_pct"]} for m in months]
    return {"war_fires_daily.csv": days[-DAILY_KEEP:], "war_fires_monthly.csv": merged}

"""Territory under Russian control, from DeepStateMap.

Source: the cyterat/deepstate-map-data archive on GitHub, one GeoJSON file per
day (data/deepstatemap_data_YYYYMMDD.geojson) from 2024-07-08, each a
MultiPolygon of Russian-occupied territory (including Crimea and areas held
before 2022). Area is geodesic (WGS84), so no projection distortion.

Runs are incremental: days already in data/processed/territory_daily.csv are
not downloaded again. Changes partly reflect DeepState redrawing its map, not
only movement on the ground; treat single-day jumps with care.
"""
from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import requests
from pyproj import Geod
from shapely.geometry import shape
from shapely.ops import unary_union

from .common import PROCESSED, USER_AGENT

BASE = "https://raw.githubusercontent.com/cyterat/deepstate-map-data/main/data/deepstatemap_data_{d}.geojson"
FIRST_DAY = date(2024, 7, 8)
SOURCE_PAGE = "https://github.com/cyterat/deepstate-map-data"
_GEOD = Geod(ellps="WGS84")


def area_km2(geojson: dict) -> float:
    feats = geojson.get("features") or [geojson]
    geom = unary_union([shape(f["geometry"]) for f in feats if f.get("geometry")])
    area, _ = _GEOD.geometry_area_perimeter(geom)
    return abs(area) / 1e6


def fetch_day(d: date, session: requests.Session) -> float | None:
    resp = session.get(BASE.format(d=d.strftime("%Y%m%d")), timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return area_km2(json.loads(resp.text))


def load_existing() -> dict[str, float]:
    path = PROCESSED / "territory_daily.csv"
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {r["date"]: float(r["occupied_km2"]) for r in csv.DictReader(f)}


def update(today: date | None = None, workers: int = 6) -> dict[str, float]:
    """Return {date: occupied km²}, downloading only days not yet computed."""
    today = today or date.today()
    known = load_existing()
    todo, d = [], FIRST_DAY
    while d <= today:
        if d.isoformat() not in known:
            todo.append(d)
        d += timedelta(days=1)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for d, km2 in zip(todo, pool.map(lambda x: fetch_day(x, session), todo)):
            if km2 is not None:
                known[d.isoformat()] = km2
    return dict(sorted(known.items()))


def daily_rows(areas: dict[str, float]) -> list[dict]:
    rows, prev = [], None
    for day, km2 in sorted(areas.items()):
        rows.append({
            "date": day, "occupied_km2": round(km2, 1),
            # change since the previous available day (gaps are rare)
            "change_km2": round(km2 - prev, 1) if prev is not None else None,
        })
        prev = km2
    return rows


def monthly_rows(daily: list[dict]) -> list[dict]:
    by_month: dict[str, list[dict]] = {}
    for r in daily:
        by_month.setdefault(r["date"][:7], []).append(r)
    out, prev_end = [], None
    for month in sorted(by_month):
        rs = by_month[month]
        end = rs[-1]["occupied_km2"]
        start = prev_end if prev_end is not None else rs[0]["occupied_km2"]
        span = (date.fromisoformat(rs[-1]["date"]) - date.fromisoformat(rs[0]["date"])).days + (1 if prev_end is not None else 0)
        out.append({
            "month": month, "days": len(rs), "end_km2": end,
            "net_change_km2": round(end - start, 1),
            "km2_per_day": round((end - start) / span, 1) if span else None,
            "complete": len(rs) >= 26,
        })
        prev_end = end
    return out

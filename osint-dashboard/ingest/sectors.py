"""Where the front moved: DeepStateMap gains and losses by front direction, plus front-line shape.

Method
- Take the first available daily map of each month (from July 2024).
- For each month: gained = new map minus old map, lost = old minus new, as
  polygons in UTM zone 37N (metres; area error under about 1% across the front).
- Drop slivers under 0.05 km²: they are mostly redrawing noise.
- Assign each piece to the nearest named front direction (anchor points below,
  placed on the town each direction is named after; accurate to a few km).
  Pieces more than 60 km from every anchor go to "Other".
- Depth of a gained piece = the furthest point of it from the old line.

Changes partly reflect DeepState redrawing its map, not only fighting.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta

import requests
from pyproj import Transformer
from shapely.geometry import Point, shape
import numpy as np
import shapely
from shapely.ops import unary_union

from .common import RAW, USER_AGENT
from .territory import BASE, FIRST_DAY

# (name, lat, lon): towns ISW and both militaries use to name directions
ANCHORS = [
    ("Kharkiv north (Vovchansk)", 50.29, 36.94),
    ("Sumy border", 51.24, 35.00),
    ("Kupiansk", 49.71, 37.62),
    ("Lyman", 48.99, 37.81),
    ("Siversk", 48.87, 38.10),
    ("Kostiantynivka", 48.53, 37.71),
    ("Toretsk", 48.40, 37.85),
    ("Pokrovsk", 48.28, 37.18),
    ("Dobropillya", 48.46, 37.08),
    ("Kurakhove", 47.98, 37.28),
    ("Novopavlivka", 48.12, 36.75),
    ("Velyka Novosilka", 47.84, 36.83),
    ("Huliaipole", 47.66, 36.26),
    ("Orikhiv", 47.57, 35.79),
    ("Kherson (Dnipro river)", 46.64, 32.62),
]
MAX_ANCHOR_KM = 60
MIN_PIECE_KM2 = 0.05
_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32637", always_xy=True).transform
_ANCHOR_PTS = [(name, Point(_TO_UTM(lon, lat))) for name, lat, lon in ANCHORS]


def fetch_map(d: date, session: requests.Session):
    """Occupied area on day d as a UTM polygon, or None if that day has no file. Cached."""
    path = RAW / "deepstate" / f"{d:%Y%m%d}.geojson"
    if path.exists():
        text = path.read_text()
    else:
        resp = session.get(BASE.format(d=d.strftime("%Y%m%d")), timeout=60)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        text = resp.text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    feats = json.loads(text).get("features", [])
    geom = unary_union([shape(f["geometry"]) for f in feats if f.get("geometry")])
    return shapely.transform(geom, lambda xy: np.column_stack(_TO_UTM(xy[:, 0], xy[:, 1]))).buffer(0)


def month_starts(today: date) -> list[date]:
    out, d = [], FIRST_DAY
    while d <= today:
        out.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def nearest_direction(pt: Point) -> str:
    name, anchor = min(_ANCHOR_PTS, key=lambda a: a[1].distance(pt))
    return name if anchor.distance(pt) <= MAX_ANCHOR_KM * 1000 else "Other"


def pieces(geom) -> list:
    if geom.is_empty:
        return []
    parts = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    return [p for p in parts if p.area / 1e6 >= MIN_PIECE_KM2]


def compare_pieces(prev, cur) -> tuple[list, list]:
    """Pieces Russia gained and lost between two maps (slivers dropped)."""
    return pieces(cur.difference(prev)), pieces(prev.difference(cur))


def compare(prev, cur) -> dict:
    """Gains and losses between two maps, by direction, with shape metrics."""
    gained, lost = compare_pieces(prev, cur)
    by_dir: dict[str, dict] = defaultdict(lambda: {"gained_km2": 0.0, "lost_km2": 0.0, "pieces": 0})
    depths = []
    for g in gained:
        d = by_dir[nearest_direction(g.representative_point())]
        d["gained_km2"] += g.area / 1e6
        d["pieces"] += 1
        ring = g.exterior.coords if hasattr(g, "exterior") else []
        depths.append(max((prev.distance(Point(c)) for c in ring), default=0.0) / 1000)
    for l in lost:
        by_dir[nearest_direction(l.representative_point())]["lost_km2"] += l.area / 1e6
    total_gain = sum(g.area for g in gained) / 1e6
    top = max(by_dir.items(), key=lambda kv: kv[1]["gained_km2"], default=(None, None))
    shape_row = {
        "gained_pieces": len(gained),
        "largest_piece_km2": round(max((g.area for g in gained), default=0) / 1e6, 1),
        "max_depth_km": round(max(depths, default=0.0), 1),
        "top_direction": top[0] or "",
        "top_direction_share": round(top[1]["gained_km2"] / total_gain, 2) if top[0] and total_gain else None,
        "gained_km2": round(total_gain, 1),
        "lost_km2": round(sum(l.area for l in lost) / 1e6, 1),
    }
    return {"by_direction": dict(by_dir), "shape": shape_row}


def run(today: date | None = None) -> dict[str, list[dict]]:
    today = today or date.today()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    snaps = []
    for start in month_starts(today):
        for k in range(5):                      # first available day of the month
            geom = fetch_map(start + timedelta(days=k), session)
            if geom is not None:
                snaps.append((start, geom))
                break
    by_dir_rows, shape_rows = [], []
    for (d0, g0), (d1, g1) in zip(snaps, snaps[1:]):
        res = compare(g0, g1)
        month = f"{d0:%Y-%m}"
        for name, v in sorted(res["by_direction"].items()):
            by_dir_rows.append({"month": month, "direction": name, "gained_km2": round(v["gained_km2"], 1),
                                "lost_km2": round(v["lost_km2"], 1), "net_km2": round(v["gained_km2"] - v["lost_km2"], 1),
                                "pieces": v["pieces"]})
        shape_rows.append({"month": month, **res["shape"]})
    return {"territory_by_direction.csv": by_dir_rows, "front_shape.csv": shape_rows}

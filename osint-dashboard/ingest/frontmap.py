"""Map layers for the dashboard's front map.

Produces one JSON list of rows, each a shape as an SVG path in kilometres
(UTM zone 37N, x east, y north; the page flips y):
- frame:    the map window (eastern and southern Ukraine)
- ukraine:  Ukraine's border (Natural Earth 1:50m)
- occupied: area DeepStateMap shows under Russian control on the latest day
- gain / loss: pieces Russia gained / lost in each of the last 12 months,
  with the month, area and nearest front direction (same method as sectors.py)
- anchor:   the named front directions, as points
- city:     a few reference cities
Shapes are simplified (occupied area to 300 m, pieces to 100 m) to keep the file small.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import requests
import shapely
from shapely.geometry import Point, box, shape

from .common import RAW, USER_AGENT
from .sectors import ANCHORS, _TO_UTM, compare_pieces, fetch_map, month_starts, nearest_direction

NE_COUNTRIES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
CITIES = [("Kharkiv", 49.99, 36.23), ("Dnipro", 48.46, 35.05), ("Zaporizhzhia", 47.84, 35.14), ("Donetsk", 48.00, 37.80),
          ("Luhansk", 48.57, 39.31), ("Mariupol", 47.10, 37.55), ("Kramatorsk", 48.72, 37.56), ("Simferopol", 44.95, 34.10)]
FRAME_LONLAT = (31.6, 44.35, 40.4, 51.6)        # lon_min, lat_min, lon_max, lat_max
MONTHS = 12


def _utm(geom):
    return shapely.transform(geom, lambda xy: np.column_stack(_TO_UTM(xy[:, 0], xy[:, 1]))).buffer(0)


def svg_path(geom, decimals: int = 2) -> str:
    """Polygon/MultiPolygon in metres -> SVG path in km."""
    parts = []
    polys = list(geom.geoms) if hasattr(geom, "geoms") else [geom]
    for poly in polys:
        if poly.is_empty or not hasattr(poly, "exterior"):
            continue
        for ring in [poly.exterior, *poly.interiors]:
            pts = [(round(x / 1000, decimals), round(y / 1000, decimals)) for x, y in ring.coords]
            parts.append("M" + "L".join(f"{x},{y}" for x, y in pts) + "Z")
    return "".join(parts)


def ukraine_border(session: requests.Session):
    path = RAW / "ne_50m_admin_0_countries.geojson"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session.get(NE_COUNTRIES, timeout=120).text)
    for f in json.loads(path.read_text())["features"]:
        if f["properties"].get("ADM0_A3") == "UKR":
            return _utm(shape(f["geometry"]))
    raise ValueError("Ukraine not found in Natural Earth countries")


def run(today: date | None = None) -> dict[str, list[dict]]:
    today = today or date.today()
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    lo_x, lo_y = _TO_UTM(FRAME_LONLAT[0], FRAME_LONLAT[1])
    hi_x, hi_y = _TO_UTM(FRAME_LONLAT[2], FRAME_LONLAT[3])
    frame = box(lo_x, lo_y, hi_x, hi_y)
    rows = [{"layer": "frame", "month": "", "side": "", "direction": "", "km2": None, "name": "",
             "x": round(lo_x / 1000, 1), "y": round(lo_y / 1000, 1),
             "w": round((hi_x - lo_x) / 1000, 1), "h": round((hi_y - lo_y) / 1000, 1), "d": ""}]
    ukr = ukraine_border(session).intersection(frame).simplify(500)
    rows.append({"layer": "ukraine", "d": svg_path(ukr)})

    latest = None
    for k in range(4):
        latest = fetch_map(today - timedelta(days=k), session)
        if latest is not None:
            latest_day = today - timedelta(days=k)
            break
    if latest is None:
        raise RuntimeError("no recent DeepStateMap file")
    rows.append({"layer": "occupied", "name": latest_day.isoformat(), "d": svg_path(latest.intersection(frame).simplify(300))})

    starts = month_starts(today)[-(MONTHS + 1):]
    snaps = []
    for s in starts:
        for k in range(5):
            g = fetch_map(s + timedelta(days=k), session)
            if g is not None:
                snaps.append((s, g))
                break
    for (d0, g0), (d1, g1) in zip(snaps, snaps[1:]):
        gained, lost = compare_pieces(g0, g1)
        for layer, pcs, side in (("gain", gained, "RU"), ("loss", lost, "UA")):
            for pc in pcs:
                rows.append({"layer": layer, "month": f"{d0:%Y-%m}", "side": side,
                             "direction": nearest_direction(pc.representative_point()),
                             "km2": round(pc.area / 1e6, 2), "d": svg_path(pc.simplify(100))})

    for name, lat, lon in ANCHORS:
        x, y = _TO_UTM(lon, lat)
        rows.append({"layer": "anchor", "name": name, "x": round(x / 1000, 1), "y": round(y / 1000, 1)})
    for name, lat, lon in CITIES:
        x, y = _TO_UTM(lon, lat)
        rows.append({"layer": "city", "name": name, "x": round(x / 1000, 1), "y": round(y / 1000, 1)})
    keys = ["layer", "month", "side", "direction", "km2", "name", "x", "y", "w", "h", "d"]
    return {"front_map.json": [{k: r.get(k, "" if k in ("month", "side", "direction", "name", "d") else None) for k in keys} for r in rows]}

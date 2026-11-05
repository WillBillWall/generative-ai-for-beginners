"""Local-boundary map: how much of each local council area changed hands.

Boundaries: geoBoundaries gbOpen UKR (CC BY 4.0, wmgeolab/geoBoundaries), which
uses Ukraine's pre-2020 units: ADM2 = raions (old districts, ~1,200 km² each)
and ADM3 = village/town councils (~58 km² each).

`build_reference` (run once, result committed) keeps the raions in the map
window and the councils within FRONT_BAND_KM of the front line on either the
first or the latest DeepStateMap day, simplified and stored in UTM 37N metres
in data/reference/admin_east.json. `run` measures, for each council, the share
of its area under Russian control on several dates, so the page can colour it
by how that share changed over the chosen period.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import requests
import shapely
from shapely.geometry import box, mapping, shape
from shapely.strtree import STRtree

from .common import DATA, USER_AGENT
from .frontmap import FRAME_LONLAT, svg_path
from .sectors import _TO_UTM, fetch_map
from .territory import FIRST_DAY

REFERENCE = DATA / "reference" / "admin_east.json"
FRONT_BAND_KM = 30
LOOKBACK = {"s_1m": 30, "s_3m": 91, "s_12m": 365}


def _utm(geom):
    return shapely.transform(geom, lambda xy: np.column_stack(_TO_UTM(xy[:, 0], xy[:, 1]))).buffer(0)


def _round(geom, step: float = 10.0):
    return shapely.set_precision(geom, step)


def build_reference(adm2_path: Path, adm3_path: Path) -> dict:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    lo_x, lo_y = _TO_UTM(FRAME_LONLAT[0], FRAME_LONLAT[1])
    hi_x, hi_y = _TO_UTM(FRAME_LONLAT[2], FRAME_LONLAT[3])
    frame = box(lo_x, lo_y, hi_x, hi_y)
    first = fetch_map(FIRST_DAY, session)
    latest = next(g for k in range(5) if (g := fetch_map(date.today() - timedelta(days=k), session)) is not None)
    band = first.boundary.union(latest.boundary).buffer(FRONT_BAND_KM * 1000)

    raions = []
    for f in json.loads(adm2_path.read_text())["features"]:
        g = _utm(shape(f["geometry"]))
        if g.intersects(frame):
            raions.append({"name": f["properties"]["shapeName"], "geometry": g})
    tree = STRtree([r["geometry"] for r in raions])

    councils = []
    for f in json.loads(adm3_path.read_text())["features"]:
        g = _utm(shape(f["geometry"]))
        if not g.intersects(band):
            continue
        idx = tree.query(g.representative_point(), predicate="within")
        councils.append({"name": f["properties"]["shapeName"],
                         "raion": raions[int(idx[0])]["name"] if len(idx) else "",
                         "geometry": g})
    out = {
        "source": "geoBoundaries gbOpen UKR ADM2/ADM3 (CC BY 4.0), pre-2020 units; UTM 37N metres",
        "front_band_km": FRONT_BAND_KM,
        "raions": [{"name": r["name"], "geometry": mapping(_round(r["geometry"].intersection(frame).simplify(400)))} for r in raions],
        "councils": [{"name": c["name"], "raion": c["raion"], "geometry": mapping(_round(c["geometry"].simplify(120)))} for c in councils],
    }
    REFERENCE.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE.write_text(json.dumps(out, separators=(",", ":")))
    return {"raions": len(raions), "councils": len(councils)}


def run(today: date | None = None) -> dict[str, list[dict]]:
    today = today or date.today()
    ref = json.loads(REFERENCE.read_text())
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    def map_near(d: date):
        for k in range(5):
            g = fetch_map(d - timedelta(days=k), session)
            if g is not None:
                return g, d - timedelta(days=k)
        raise RuntimeError(f"no DeepStateMap file near {d}")

    now, now_day = map_near(today)
    maps = {"s_now": now, "s_start": map_near(FIRST_DAY + timedelta(days=4))[0]}
    for key, days in LOOKBACK.items():
        maps[key] = map_near(today - timedelta(days=days))[0]

    rows = [{"layer": "raion", "name": r["name"], "d": svg_path(shape(r["geometry"]), 1)} for r in ref["raions"]]
    for c in ref["councils"]:
        g = shape(c["geometry"])
        area = g.area
        if area <= 0:
            continue
        row = {"layer": "unit", "name": c["name"], "raion": c["raion"], "area_km2": round(area / 1e6, 1)}
        for key, m in maps.items():
            row[key] = round(g.intersection(m).area / area, 3)
        row["d"] = svg_path(g, 1)
        rows.append(row)
    rows.append({"layer": "meta", "name": now_day.isoformat()})
    return {"local_map.json": rows}


if __name__ == "__main__":
    # python -m ingest.admin <ADM2.geojson> <ADM3.geojson>
    print(build_reference(Path(sys.argv[1]), Path(sys.argv[2])))

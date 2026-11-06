"""Equipment-loss ingest.

Sources
- UA MoD daily cumulative claims of Russian losses, via the community mirror
  PetroIvaniuk/2022-Ukraine-Russia-War-Dataset (GitHub). Method: claimed.
- Oryx model-level totals of Russian losses (same mirror, snapshot without dates).
  Method: visually_confirmed.
- WarSpotting per-loss records (dated, both sides). Method: visually_confirmed.
  Its API was unreachable from the build environment; parse_warspotting() is
  tested against a fixture only.

Every function returns rows that match schema/losses.schema.json.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from .common import RAW, WAR_START, polite_get, quarter_bounds, quarter_of

MIRROR = "https://raw.githubusercontent.com/PetroIvaniuk/2022-Ukraine-Russia-War-Dataset/main/data"
UA_MOD_URL = f"{MIRROR}/russia_losses_equipment.json"
ORYX_URL = f"{MIRROR}/russia_losses_equipment_oryx.json"
# Last commit touching the Oryx file in the mirror (git log, checked 2026-11-04).
# The mirror stopped updating it, so the snapshot is old: label it honestly.
ORYX_AS_OF = "2023-02-05"
WARSPOTTING_API = "https://ukr.warspotting.net/api/losses/{side}/{date}/{page}/"  # trailing slash avoids a redirect

# UA MoD field -> equipment class. Field names changed over time
# ('military auto' + 'fuel tank' were merged into 'vehicles and fuel tanks').
UA_MOD_FIELDS = {
    "tank": "tank",
    "APC": "afv",
    "field artillery": "artillery",
    "MRL": "mrl",
    "anti-aircraft warfare": "air_defense",
    "aircraft": "aircraft",
    "helicopter": "helicopter",
    "drone": "uav",
    "ground robotic systems": "ugv",
    "cruise missiles": "cruise_missile",
    "naval ship": "naval",
    "submarines": "naval",
    "military auto": "vehicles",
    "fuel tank": "vehicles",
    "vehicles and fuel tanks": "vehicles",
    "special equipment": "special_equipment",
}

ORYX_CATEGORIES = {
    "Tanks": "tank",
    "Armoured Fighting Vehicles": "afv",
    "Infantry Fighting Vehicles": "afv",
    "Armoured Personnel Carriers": "afv",
    "Mine-Resistant Ambush Protected": "afv",
    "Infantry Mobility Vehicles": "afv",
    "Self-Propelled Artillery": "artillery",
    "Towed Artillery": "artillery",
    "Multiple Rocket Launchers": "mrl",
    "Self-Propelled Anti-Aircraft Guns": "air_defense",
    "Surface-To-Air Missile Systems": "air_defense",
    "Aircraft": "aircraft",
    "Helicopters": "helicopter",
    "Unmanned Aerial Vehicles": "uav",
    "Reconnaissance Unmanned Aerial Vehicles": "uav",
    "Unmanned Combat Aerial Vehicles": "uav",
    "Self-Propelled Anti-Tank Missile Systems": "afv",
    "Anti-Aircraft Guns": "air_defense",
    "Radars": "ew_radar",
    "Jammers And Deception Systems": "ew_radar",
    "Command Posts And Communications Stations": "command_comms",
    "Naval Ships": "naval",
    "Naval Ships and Submarines": "naval",
    "Trucks, Vehicles and Jeeps": "vehicles",
    "Engineering Vehicles And Equipment": "special_equipment",
}


def fetch_json(url: str, cache_name: str, refresh: bool) -> list:
    path = RAW / cache_name
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(polite_get(url).text)
    return json.loads(path.read_text())


def ua_mod_daily_deltas(records: list[dict]) -> list[tuple[str, str, int]]:
    """Daily cumulative totals -> (date, equipment class, losses that day).

    Cumulative series can dip when the MoD corrects a figure; negative daily
    deltas are kept so period sums still equal the change in the total.
    A class first reported after day one (e.g. ground robotic systems from
    2026-05-03) arrives with a back-filled cumulative total; that first value
    is a baseline, not losses on that day, so it is not counted.
    """
    records = sorted(records, key=lambda r: r["date"])
    first_day = records[0]["date"] if records else None
    prev: dict[str, int] = {}
    out = []
    for rec in records:
        day_totals: dict[str, int] = defaultdict(int)
        for field, cls in UA_MOD_FIELDS.items():
            v = rec.get(field)
            if isinstance(v, (int, float)):
                day_totals[cls] += int(v)
        for cls, total in day_totals.items():
            baseline = cls not in prev and rec["date"] != first_day
            out.append((rec["date"], cls, 0 if baseline else total - prev.get(cls, 0)))
            prev[cls] = total
    return out


def ua_mod_quarterly(records: list[dict]) -> list[dict]:
    """Daily cumulative totals -> per-quarter increments per equipment class."""
    records = sorted(records, key=lambda r: r["date"])
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for day, cls, n in ua_mod_daily_deltas(records):
        totals[(quarter_of(day), cls)] += n
    last = records[-1]["date"] if records else None
    rows = []
    for (q, cls), n in sorted(totals.items()):
        start, end = quarter_bounds(q)
        start = max(start, WAR_START)
        if last and end.isoformat() > last:
            end = date.fromisoformat(last)
        rows.append({
            "period_start": start.isoformat(), "period_end": end.isoformat(),
            "side": "RU", "equipment_class": cls, "model": "*", "count": max(n, 0),
            "source_org": "UA MoD", "method": "claimed", "source_url": UA_MOD_URL,
        })
    return rows


def oryx_snapshot(records: list[dict], as_of: str = ORYX_AS_OF) -> list[dict]:
    """Oryx model totals (no dates) -> one cumulative row per model."""
    rows = []
    for rec in records:
        cls = ORYX_CATEGORIES.get(rec.get("equipment_oryx", ""), "other")
        rows.append({
            "period_start": "2022-02-24", "period_end": as_of,
            "side": "RU", "equipment_class": cls,
            "model": rec.get("model", "?"), "count": int(rec.get("losses_total", 0)),
            "source_org": "Oryx", "method": "visually_confirmed", "source_url": ORYX_URL,
        })
    return rows


def parse_warspotting(payload: dict, side: str) -> list[dict]:
    """WarSpotting losses page -> one row per (day, class, model).

    Expected shape: {"losses": [{"date": "YYYY-MM-DD", "type": "...",
    "model": "...", "id": 123}, ...]}. Unknown types map to 'other'.
    """
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for loss in payload.get("losses", []):
        cls = ORYX_CATEGORIES.get(loss.get("type", ""), "other")
        counts[(loss["date"][:10], cls, loss.get("model") or "?")] += 1
    return [{
        "period_start": d, "period_end": d, "side": side, "equipment_class": cls,
        "model": model, "count": n, "source_org": "WarSpotting",
        "method": "visually_confirmed", "source_url": "https://ukr.warspotting.net/",
    } for (d, cls, model), n in sorted(counts.items())]


def fetch_warspotting(side: str, day: date, max_pages: int = 20) -> list[dict]:
    """side: 'russia' or 'ukraine'. Network access to warspotting.net required."""
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        resp = polite_get(WARSPOTTING_API.format(side=side, date=day.isoformat(), page=page))
        payload = resp.json()
        if not payload.get("losses"):
            break
        rows += parse_warspotting(payload, "RU" if side == "russia" else "UA")
    return rows


def run(refresh: bool = False) -> list[dict]:
    mod = fetch_json(UA_MOD_URL, "ua_mod_equipment.json", refresh)
    oryx = fetch_json(ORYX_URL, "oryx_models.json", refresh)
    return ua_mod_quarterly(mod) + oryx_snapshot(oryx)


def ua_mod_cumulative_on(records: list[dict], day: str) -> dict[str, int]:
    """UA MoD cumulative claimed totals per class on a given day."""
    rec = max((r for r in records if r["date"] <= day), key=lambda r: r["date"])
    out: dict[str, int] = defaultdict(int)
    for field, cls in UA_MOD_FIELDS.items():
        if isinstance(rec.get(field), (int, float)):
            out[cls] += int(rec[field])
    return dict(out)


def claimed_vs_confirmed(refresh: bool = False) -> list[dict]:
    """UA MoD claimed vs Oryx visually confirmed Russian losses on ORYX_AS_OF."""
    mod = fetch_json(UA_MOD_URL, "ua_mod_equipment.json", refresh)
    oryx = fetch_json(ORYX_URL, "oryx_models.json", refresh)
    claimed = ua_mod_cumulative_on(mod, ORYX_AS_OF)
    confirmed: dict[str, int] = defaultdict(int)
    for r in oryx_snapshot(oryx):
        confirmed[r["equipment_class"]] += r["count"]
    return [{"equipment_class": c, "as_of": ORYX_AS_OF, "ua_mod_claimed": claimed[c],
             "oryx_confirmed": confirmed[c],
             "claimed_to_confirmed": round(claimed[c] / confirmed[c], 2)}
            for c in ("tank", "afv", "artillery", "mrl", "air_defense", "aircraft", "helicopter")
            if confirmed.get(c) and claimed.get(c)]

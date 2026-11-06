"""WarSpotting: photo-confirmed Russian equipment losses, one record per loss.

API (https://ukr.warspotting.net/api/docs/): /api/losses/russia/<ID>/ returns up to
100 losses from that ID upward. Only Russian losses are tracked. Requests need a
User-Agent and must stay under 10 per 10 seconds; we use about one a second.

WarSpotting's data is "all rights reserved": raw records stay in the gitignored
data/raw cache, and only aggregate counts are published, credited to WarSpotting.
New finds always get new IDs (even for old dates), so later runs fetch only IDs
above the highest cached one. A full fetch takes several minutes.

Outputs
- warspotting_monthly.csv: confirmed losses per month by equipment class and status
- warspotting_adaptations.csv: per month, confirmed tank/armoured-vehicle losses and the share
  carrying anti-drone cages, jammers, turtle armour, mine ploughs, extra armour (from tags)
- claimed_vs_confirmed_live.csv: UA MoD claimed vs WarSpotting confirmed, cumulative to today
"""
from __future__ import annotations

import json
import time
from collections import defaultdict

import requests

from .common import RAW, USER_AGENT
from .losses import UA_MOD_URL, fetch_json, ua_mod_cumulative_on

API = "https://ukr.warspotting.net/api/losses/russia/{start}/"
CACHE = RAW / "warspotting_russia.json"
SOURCE_URL = "https://ukr.warspotting.net/"

# WarSpotting equipment type (as the API names them) -> our equipment classes (taxonomy.yaml)
TYPE_CLASS = {
    "Tanks": "tank",
    "Infantry fighting vehicles": "afv", "Infantry mobility vehicles": "afv", "Anti-tank systems": "afv",
    "Self-propelled artillery": "artillery", "Towed artillery": "artillery",
    "Rocket and missile artillery": "mrl",
    "Anti-aircraft systems": "air_defense",
    "Airplanes": "aircraft", "Helicopters": "helicopter",
    "Drones": "uav", "Vessels": "naval",
    "Transport": "vehicles", "Ambulances, medical vehicles": "vehicles",
    "Engineering": "special_equipment", "Radars, jammers": "ew_radar",
    "Command posts, communication": "command_comms",
}

# WarSpotting tags mostly describe the lost vehicle, not the weapon that hit it.
# These groups track how Russian armour was adapted against drones and mines.
ADAPTATIONS = {
    "Cope cage": "Anti-drone cage",
    "Jammer": "Vehicle-mounted jammer",
    "Turtle": "Full-cover 'turtle' armour",
    "Hedgehog": "Full-cover 'turtle' armour",
    "Additional armour": "Extra armour",
    "Mine plow/roller": "Mine plough or roller",
    "Improvised": "Improvised vehicle",
}
ARMOUR = {"tank", "afv"}


def fetch(session: requests.Session | None = None, pause: float = 1.1) -> list[dict]:
    """All Russian losses, using the cache and fetching only IDs above the highest cached one."""
    session = session or requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    known = {r["id"]: r for r in json.loads(CACHE.read_text())} if CACHE.exists() else {}
    start = max(known, default=0) + 1
    while True:
        resp = session.get(API.format(start=start), timeout=60)
        resp.raise_for_status()
        batch = resp.json().get("losses", [])
        if not batch:
            break
        for r in batch:
            known[r["id"]] = r
        nxt = max(r["id"] for r in batch) + 1
        if nxt <= start:
            break
        start = nxt
        time.sleep(pause)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(list(known.values())))
    return list(known.values())


def equipment_class(type_name: str) -> str:
    return TYPE_CLASS.get(type_name or "", "other")


def adaptations(tags: str | None) -> list[str]:
    """Adaptation groups named in a record's tags (none, one or several)."""
    found = []
    for raw in str(tags or "").split(","):
        group = ADAPTATIONS.get(raw.strip())
        if group and group not in found:
            found.append(group)
    return found


def monthly(records: list[dict]) -> list[dict]:
    counts: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        if not r.get("date"):
            continue
        key = (r["date"][:7], equipment_class(r.get("type")))
        counts[key][(r.get("status") or "unknown").lower()] += 1
    out = []
    for (month, cls), c in sorted(counts.items()):
        out.append({"month": month, "equipment_class": cls,
                    "destroyed": c["destroyed"], "damaged": c["damaged"], "abandoned": c["abandoned"],
                    "captured": c["captured"], "total": sum(c.values())})
    return out


def adaptation_monthly(records: list[dict]) -> list[dict]:
    """Per month: confirmed losses of tanks and armoured vehicles, and the share carrying each adaptation."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        if not r.get("date") or equipment_class(r.get("type")) not in ARMOUR:
            continue
        month = r["date"][:7]
        counts[month]["_armour"] += 1
        for a in adaptations(r.get("tags")):
            counts[month][a] += 1
    groups = sorted(set(ADAPTATIONS.values()))
    out = []
    for m in sorted(counts):
        n = counts[m]["_armour"]
        row = {"month": m, "armour_losses": n}
        for g in groups:
            row[g] = counts[m][g]
            row[f"{g} share"] = round(counts[m][g] / n, 3) if n else None
        out.append(row)
    return out


def claimed_vs_confirmed(records: list[dict], refresh: bool = False) -> list[dict]:
    mod = fetch_json(UA_MOD_URL, "ua_mod_equipment.json", refresh)
    as_of = max(r["date"] for r in mod)
    claimed = ua_mod_cumulative_on(mod, as_of)
    confirmed: dict[str, int] = defaultdict(int)
    for r in records:
        if r.get("date") and r["date"] <= as_of:
            confirmed[equipment_class(r.get("type"))] += 1
    out = []
    for c in ("tank", "afv", "artillery", "mrl", "air_defense", "aircraft", "helicopter"):
        if confirmed.get(c) and claimed.get(c):
            out.append({"equipment_class": c, "as_of": as_of, "ua_mod_claimed": claimed[c],
                        "warspotting_confirmed": confirmed[c],
                        "claimed_to_confirmed": round(claimed[c] / confirmed[c], 2)})
    return out


def run(refresh: bool = False) -> dict[str, list[dict]]:
    records = fetch() if (refresh or not CACHE.exists()) else json.loads(CACHE.read_text())
    return {"warspotting_monthly.csv": monthly(records),
            "warspotting_adaptations.csv": adaptation_monthly(records),
            "claimed_vs_confirmed_live.csv": claimed_vs_confirmed(records, refresh)}

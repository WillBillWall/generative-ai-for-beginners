"""Validate, normalize and aggregate every source into data/processed/.

    python normalize.py build [--refresh]        # rebuild processed tables (offline from cache)
    python normalize.py isw 2026-10-17           # code one ISW daily assessment with Claude
    python normalize.py rusi <pdf_url> "<title>" 2025-02-14

Coded observations from `isw`/`rusi` land in data/extracted/*.jsonl and are
merged with data/seed/observations.csv on the next build.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import jsonschema

from ingest import correlate, equipment, frontmap, losses, sectors, territory, trends
from ingest.common import DATA, PROCESSED, SCHEMA, SEED, quarter_of, sides_of, taxonomy

EXTRACTED = DATA / "extracted"
# RUSI and ISW are analytic sources: their rows are expert assessments that go on
# the tactic timeline. They never feed loss counts, which come only from loss
# trackers (see losses.schema.json source_org).
ASSESSED_ORGS = {"ISW", "RUSI", "Other think tank"}
OBS_FIELDS = json.loads((SCHEMA / "observation.schema.json").read_text())["required"]


class ValidationError(ValueError):
    pass


def _validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(json.loads((SCHEMA / name).read_text()))


def obs_id(row: dict) -> str:
    key = f"{row['source_url']}|{row['tactic_subtype']}|{row['side']}|{row['summary']}"
    return f"{row['source_org'].lower().replace(' ', '')}-{row['date']}-{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def validate_observation(row: dict) -> dict:
    row = {k: (row.get(k) or "") for k in OBS_FIELDS}
    errors = [e.message for e in _validator("observation.schema.json").iter_errors(row)]
    cats = taxonomy()["categories"]
    if row["tactic_category"] not in cats:
        errors.append(f"unknown category {row['tactic_category']!r}")
    elif row["tactic_subtype"] not in cats[row["tactic_category"]]["subtypes"]:
        errors.append(f"subtype {row['tactic_subtype']!r} not in {row['tactic_category']}")
    if row["stage"] not in taxonomy()["stages"]:
        errors.append(f"unknown stage {row['stage']!r}")
    if errors:
        raise ValidationError(f"{row.get('id') or '?'}: " + "; ".join(errors))
    return row


def validate_loss(row: dict) -> dict:
    errors = [e.message for e in _validator("losses.schema.json").iter_errors(row)]
    if row.get("equipment_class") not in taxonomy()["equipment_classes"]:
        errors.append(f"unknown class {row.get('equipment_class')!r}")
    if errors:
        raise ValidationError("; ".join(errors))
    return row


def load_observations() -> list[dict]:
    with (SEED / "observations.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    for path in sorted(EXTRACTED.glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    seen, out = set(), []
    for row in rows:
        row["id"] = row.get("id") or obs_id(row)
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append(validate_observation(row))
    out = sorted(out, key=lambda r: (r["date"], r["id"]))
    check_stage_order(out)
    return out


STAGE_RANK = {"emerging": 0, "spreading": 1, "widespread": 2, "fading": 3}


def check_stage_order(rows: list[dict]) -> None:
    """Within one row (tactic + side) and one sector, stages only move forward.

    A lower stage than the previous report is allowed only when it is
    `resurgent` (after fading) or when the report is about a different sector,
    which is a new place where the tactic is starting again.
    """
    last: dict[tuple[str, str], dict] = {}
    problems = []
    for r, side in ((r, s) for r in rows for s in sides_of(r)):
        key = (r["tactic_subtype"], side)
        prev = last.get(key)
        if prev:
            if r["stage"] == "resurgent" and prev["stage"] not in ("fading", "resurgent"):
                problems.append(f"{r['id']}: 'resurgent' must follow 'fading', not {prev['stage']!r}")
            same_place = r["sector"] == prev["sector"]
            if (same_place and r["stage"] in STAGE_RANK and prev["stage"] in STAGE_RANK
                    and STAGE_RANK[r["stage"]] < STAGE_RANK[prev["stage"]]):
                problems.append(f"{r['id']}: stage went back from {prev['stage']!r} ({prev['id']}) to "
                                f"{r['stage']!r} in the same sector; use 'resurgent' or a sector")
        last[key] = r
    if problems:
        raise ValidationError("stage order: " + " | ".join(problems))


def load_metrics() -> list[dict]:
    """Seed tactical metrics, validated against schema/metric.schema.json and the taxonomy."""
    v = _validator("metric.schema.json")
    tax = taxonomy()["metrics"]
    with (SEED / "metrics.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        for k in ("value", "value_low", "value_high"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
        errors = [e.message for e in v.iter_errors(r)]
        if r["metric"] not in tax:
            errors.append(f"unknown metric {r['metric']!r}")
        if errors:
            raise ValidationError(f"{r.get('id')}: " + "; ".join(errors))
        out.append({**r, "metric_label": tax[r["metric"]]["label"], "unit": tax[r["metric"]]["unit"]})
    return sorted(out, key=lambda r: (r["metric"], r["date"]))


def tactic_shift(quarterly: list[dict]) -> list[dict]:
    """Per-quarter daily rates of claimed Russian losses and the drone:armor ratio."""
    by_q: dict[str, dict] = defaultdict(dict)
    for r in quarterly:
        q = quarter_of(r["period_start"])
        by_q[q][r["equipment_class"]] = r["count"]
        by_q[q]["_days"] = (date.fromisoformat(r["period_end"]) - date.fromisoformat(r["period_start"])).days + 1
    out = []
    for q in sorted(by_q):
        v, days = by_q[q], by_q[q]["_days"]
        armor = v.get("tank", 0) + v.get("afv", 0)
        out.append({
            "quarter": q, "days": days,
            "tanks_per_day": round(v.get("tank", 0) / days, 2),
            "afv_per_day": round(v.get("afv", 0) / days, 2),
            "artillery_per_day": round(v.get("artillery", 0) / days, 2),
            "uav_per_day": round(v.get("uav", 0) / days, 1),
            "ugv_per_day": round(v.get("ugv", 0) / days, 2),
            "drones_per_armored_vehicle": round(v.get("uav", 0) / armor, 1) if armor else None,
        })
    return out


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(rows, separators=(",", ":")))
        return
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def build(refresh: bool = False, territory_refresh: bool = False) -> dict[str, int]:
    obs = load_observations()
    cats = taxonomy()["categories"]
    for r in obs:
        r["quarter"] = quarter_of(r["date"])
        r["category_label"] = cats[r["tactic_category"]]["label"]
        r["subtype_label"] = cats[r["tactic_category"]]["subtypes"][r["tactic_subtype"]]
        r["evidence"] = "assessed" if r["source_org"] in ASSESSED_ORGS else "reported"
        r["subtype_phrase"] = taxonomy().get("phrases", {}).get(r["tactic_subtype"], r["subtype_label"].lower())
    loss_rows = [validate_loss(r) for r in losses.run(refresh=refresh)]
    mod = [r for r in loss_rows if r["source_org"] == "UA MoD"]
    oryx = [r for r in loss_rows if r["source_org"] == "Oryx"]
    oryx_by_class: dict[str, int] = defaultdict(int)
    for r in oryx:
        oryx_by_class[r["equipment_class"]] += r["count"]
    labels = taxonomy()["equipment_classes"]
    outputs = {
        "observations.csv": obs,
        "losses_quarterly.csv": mod,
        "oryx_models.csv": oryx,
        "oryx_by_class.csv": [{"equipment_class": c, "label": labels[c], "count": n,
                               "as_of": oryx[0]["period_end"]}
                              for c, n in sorted(oryx_by_class.items(), key=lambda kv: -kv[1])],
        "tactic_shift.csv": tactic_shift(mod),
        "claimed_vs_confirmed.csv": losses.claimed_vs_confirmed(),
    }
    monthly = trends.monthly_rates(losses.fetch_json(losses.UA_MOD_URL, "ua_mod_equipment.json", False))
    adapt = trends.adaptation(obs)
    outputs |= {
        "monthly.csv": monthly,
        "trend_rates.csv": trends.trend_rates(monthly),
        "shift_points.csv": trends.shift_points(monthly, obs),
        "adaptation.csv": adapt,
        "adaptation_by_year.csv": trends.adaptation_by_year(adapt),
    }
    if refresh or not (PROCESSED / "territory_daily.csv").exists() or territory_refresh:
        tdaily = territory.daily_rows(territory.update())
    else:
        tdaily = territory.daily_rows(territory.load_existing())
    tmonthly = territory.monthly_rows(tdaily)
    outputs |= {"territory_daily.csv": tdaily, "territory_monthly.csv": tmonthly}
    outputs |= correlate.run(tmonthly, monthly, obs, refresh=refresh)
    outputs |= sectors.run()
    outputs |= frontmap.run()
    mod_raw = losses.fetch_json(losses.UA_MOD_URL, "ua_mod_equipment.json", False)
    oryx_raw = losses.fetch_json(losses.ORYX_URL, "oryx_models.json", False)
    outputs |= {"equipment_monthly.csv": equipment.equipment_monthly(mod_raw),
                "oryx_tank_age.csv": equipment.oryx_tank_age(oryx_raw),
                "metrics.csv": load_metrics()}
    for name, rows in outputs.items():
        write_csv(PROCESSED / name, rows)
    return {k: len(v) for k, v in outputs.items()}


def _append_extracted(name: str, rows: list[dict]) -> None:
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    good = []
    for r in rows:
        r["id"] = obs_id(r)
        try:
            good.append(validate_observation(r))
        except ValidationError as e:
            print(f"skipped: {e}", file=sys.stderr)
    with (EXTRACTED / f"{name}.jsonl").open("a") as f:
        f.writelines(json.dumps(r) + "\n" for r in good)
    print(f"{len(good)} observations added ({len(rows) - len(good)} rejected)")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--refresh", action="store_true", help="re-download loss data")
    i = sub.add_parser("isw")
    i.add_argument("date", type=date.fromisoformat)
    r = sub.add_parser("rusi")
    r.add_argument("url")
    r.add_argument("title")
    r.add_argument("date", type=date.fromisoformat)
    args = p.parse_args(argv)

    if args.cmd == "build":
        for name, n in build(args.refresh).items():
            print(f"{name:24} {n:>6} rows")
    else:
        from ingest import reports
        if args.cmd == "isw":
            _append_extracted("isw", reports.isw_day(args.date))
        else:
            _append_extracted("rusi", reports.rusi_paper(args.url, args.title, args.date))


if __name__ == "__main__":
    main()

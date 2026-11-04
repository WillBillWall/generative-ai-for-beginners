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

from ingest import losses
from ingest.common import DATA, PROCESSED, SCHEMA, SEED, quarter_of, taxonomy

EXTRACTED = DATA / "extracted"
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
    if row["phase"] not in taxonomy()["phases"]:
        errors.append(f"unknown phase {row['phase']!r}")
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
    return sorted(out, key=lambda r: (r["date"], r["id"]))


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
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def build(refresh: bool = False) -> dict[str, int]:
    obs = load_observations()
    cats = taxonomy()["categories"]
    for r in obs:
        r["quarter"] = quarter_of(r["date"])
        r["category_label"] = cats[r["tactic_category"]]["label"]
        r["subtype_label"] = cats[r["tactic_category"]]["subtypes"][r["tactic_subtype"]]
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

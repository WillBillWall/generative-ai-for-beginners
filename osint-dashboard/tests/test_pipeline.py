import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import normalize
from ingest import extract, losses, reports
from ingest.common import quarter_bounds, quarter_of, quarters_between

FIX = Path(__file__).parent / "fixtures"


def test_quarters():
    assert quarter_of("2022-02-24") == "2022Q1"
    assert quarter_of("2026-12-31") == "2026Q4"
    assert [d.isoformat() for d in quarter_bounds("2024Q1")] == ["2024-01-01", "2024-03-31"]
    assert [d.isoformat() for d in quarter_bounds("2025Q4")] == ["2025-10-01", "2025-12-31"]
    from datetime import date
    assert quarters_between(date(2022, 2, 24), date(2022, 11, 1)) == ["2022Q1", "2022Q2", "2022Q3", "2022Q4"]


def test_ua_mod_quarterly_deltas_rename_and_baseline():
    recs = [
        {"date": "2022-02-25", "tank": 80, "military auto": 100, "fuel tank": 60},
        {"date": "2022-03-31", "tank": 100, "military auto": 150, "fuel tank": 60},
        # rename: vehicles merged into one field, cumulative continues
        {"date": "2022-04-01", "tank": 110, "vehicles and fuel tanks": 215},
        # new class appears with a back-filled total: baseline, not a loss
        {"date": "2022-04-02", "tank": 111, "vehicles and fuel tanks": 215, "ground robotic systems": 500},
        {"date": "2022-04-03", "tank": 111, "vehicles and fuel tanks": 215, "ground robotic systems": 503},
    ]
    rows = {(r["period_start"], r["equipment_class"]): r for r in losses.ua_mod_quarterly(recs)}
    assert rows[("2022-02-24", "tank")]["count"] == 100      # clamped to war start
    assert rows[("2022-02-24", "vehicles")]["count"] == 210
    assert rows[("2022-04-01", "tank")]["count"] == 11
    assert rows[("2022-04-01", "vehicles")]["count"] == 5
    assert rows[("2022-04-01", "ugv")]["count"] == 3
    assert rows[("2022-04-01", "tank")]["period_end"] == "2022-04-03"
    for r in rows.values():
        normalize.validate_loss(r)


def test_tactic_shift_rates():
    rows = losses.ua_mod_quarterly([
        {"date": "2024-01-01", "tank": 0, "APC": 0, "drone": 0},
        {"date": "2024-03-31", "tank": 91, "APC": 9, "drone": 1000},
    ])
    (q,) = normalize.tactic_shift(rows)
    assert q["days"] == 91 and q["tanks_per_day"] == 1.0
    assert q["drones_per_armored_vehicle"] == 10.0


def test_oryx_and_warspotting_mapping():
    oryx = losses.oryx_snapshot([{"equipment_oryx": "Tanks", "model": "T-72B3", "losses_total": 5},
                                 {"equipment_oryx": "Odd thing", "model": "X", "losses_total": 1}])
    assert [r["equipment_class"] for r in oryx] == ["tank", "other"]
    ws = losses.parse_warspotting(json.loads((FIX / "warspotting.json").read_text()), "RU")
    assert {(r["equipment_class"], r["count"]) for r in ws} == {("tank", 2), ("afv", 1)}
    for r in oryx + ws:
        normalize.validate_loss(r)


def test_seed_observations_valid():
    rows = normalize.load_observations()
    assert len(rows) >= 30
    assert all(r["source_url"].startswith("https://") for r in rows)
    assert len({r["id"] for r in rows}) == len(rows)


def test_validation_rejects_off_taxonomy():
    row = dict(normalize.load_observations()[0], tactic_subtype="laser_sharks")
    with pytest.raises(normalize.ValidationError, match="laser_sharks"):
        normalize.validate_observation(row)


def test_html_and_isw_slug():
    text = reports.html_to_text((FIX / "isw.html").read_text())
    assert "small-group infiltration" in text and "Subscribe" not in text
    from datetime import date
    assert reports.isw_slug(date(2026, 7, 2)) == "july-2-2026"


def test_extract_with_fake_client():
    payload = {"observations": [{
        "date": "2026-07-02", "side": "RU", "sector": "Pokrovsk", "unit": "",
        "tactic_category": "assault", "tactic_subtype": "small_group_infiltration",
        "phase": "dominant", "summary": "Small groups infiltrating.", "confidence": "high"}]}
    captured = {}

    class FakeMessages:
        def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=json.dumps(payload))])

    client = SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages()))
    rows = extract.extract_observations("text", source_org="ISW", source_title="ROCA",
                                        source_url="https://example.org/r", report_date="2026-07-02",
                                        client=client)
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_config"]["format"]["type"] == "json_schema"
    row = dict(rows[0], id=normalize.obs_id(rows[0]))
    normalize.validate_observation(row)

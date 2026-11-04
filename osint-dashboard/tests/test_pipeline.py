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


def test_rusi_is_assessed_context_never_counts():
    normalize.build()
    import csv
    rows = list(csv.DictReader((normalize.PROCESSED / "observations.csv").open()))
    rusi = [r for r in rows if r["source_org"] == "RUSI"]
    assert rusi and all(r["evidence"] == "assessed" for r in rusi)
    bad = {"period_start": "2024-01-01", "period_end": "2024-03-31", "side": "RU", "equipment_class": "tank",
           "model": "*", "count": 1, "source_org": "RUSI", "method": "claimed", "source_url": "https://rusi.org/"}
    with pytest.raises(normalize.ValidationError):
        normalize.validate_loss(bad)


# --- trend analysis -------------------------------------------------------
from ingest import trends


def test_log_trend_known_growth():
    rates = [10 * 2 ** (i / 3) for i in range(12)]          # doubles every 3 months
    fit = trends.log_trend(rates)
    assert fit["per_quarter_pct"] == pytest.approx(100.0, abs=0.1)
    assert fit["doubling_months"] == pytest.approx(3.0, abs=0.05)
    assert fit["r2"] == pytest.approx(1.0)
    falling = trends.log_trend([100 * 0.5 ** (i / 6) for i in range(12)])
    assert falling["doubling_months"] == pytest.approx(-6.0, abs=0.05)  # halving time


def test_segment_finds_known_break():
    y = [0.0] * 12 + [3.0 + 0.1 * i for i in range(12)]
    assert trends.segment(y) == [12]
    assert trends.segment([0.1 * i for i in range(24)]) == []   # straight line: no break


def test_monthly_rates_days_and_ratios():
    recs = [{"date": "2022-02-25", "tank": 10, "APC": 10, "field artillery": 5, "MRL": 5, "drone": 0},
            {"date": "2022-02-28", "tank": 20, "APC": 20, "field artillery": 10, "MRL": 10, "drone": 4},
            {"date": "2022-03-31", "tank": 51, "APC": 20, "field artillery": 10, "MRL": 10, "drone": 4}]
    feb, mar = trends.monthly_rates(recs)
    assert (feb["days"], feb["complete"]) == (5, False)      # 24-28 Feb
    assert feb["tank_per_day"] == 4.0
    assert (mar["days"], mar["complete"]) == (31, True)
    assert mar["tank_per_day"] == 1.0
    assert feb["fires_per_armor_3m"] == 0.5                  # (10+10)/(20+20)


def test_adaptation_timing():
    base = {"subtype_label": "x", "category_label": "y", "side": "RU"}
    obs = [dict(base, tactic_subtype="a", date="2024-01-01", phase="emerging"),
           dict(base, tactic_subtype="a", date="2024-07-01", phase="scaling"),
           dict(base, tactic_subtype="a", date="2025-01-01", phase="countered"),
           dict(base, tactic_subtype="b", date="2024-03-01", phase="dominant"),
           dict(base, tactic_subtype="b", date="2024-05-01", phase="scaling")]
    a, b = trends.adaptation(obs)
    assert a["months_to_spread"] == pytest.approx(6.0, abs=0.1)
    assert a["months_to_counter"] == pytest.approx(12.0, abs=0.1)
    assert b["months_to_spread"] is None                     # never reached a higher stage
    assert trends.adaptation_by_year([a, b]) == [{"first_year": 2024, "tactics": 1, "median_months_to_spread": 6.0}]


def test_growth_index_baseline_is_spring_2022():
    recs, total = [], 0
    from datetime import date, timedelta
    d = date(2022, 2, 25)
    while d <= date(2022, 9, 30):
        total += 2 if d < date(2022, 7, 1) else 6       # 2/day in spring, 6/day from July
        recs.append({"date": d.isoformat(), "tank": total})
        d += timedelta(days=1)
    rows = {r["month"]: r for r in trends.monthly_rates(recs)}
    assert rows["2022-06"]["tank_index_3m"] == 1.0
    assert rows["2022-09"]["tank_index_3m"] == 3.0


# --- territory ------------------------------------------------------------
from ingest import territory


def test_geodesic_area_of_one_degree_cell():
    cell = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}}
    assert territory.area_km2({"features": [cell]}) == pytest.approx(12308.8, rel=1e-3)


def test_territory_daily_and_monthly():
    areas = {"2025-01-30": 100.0, "2025-01-31": 103.0, "2025-02-01": 104.0, "2025-02-28": 112.0}
    daily = territory.daily_rows(areas)
    assert [r["change_km2"] for r in daily] == [None, 3.0, 1.0, 8.0]
    jan, feb = territory.monthly_rows(daily)
    assert jan["net_change_km2"] == 3.0 and feb["net_change_km2"] == 9.0   # Feb measured from Jan's last day
    assert feb["km2_per_day"] == pytest.approx(9 / 28, abs=0.05)

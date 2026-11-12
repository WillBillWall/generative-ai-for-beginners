from ingest import oryx_daily
from ingest.common import taxonomy


def row(country, kind, total, destroyed=0, damaged=0, abandoned=0, captured=0):
    return {"country": country, "equipment_type": kind, "destroyed": str(destroyed),
            "abandoned": str(abandoned), "captured": str(captured), "damaged": str(damaged),
            "type_total": str(total)}


SUMMARY = ("Losses of Armoured Combat Vehicles [Tanks, AFVs, IFVs, APCs, and MRAPs] - 14203, "
           "of which: destroyed: 11223, damaged: 383, abandoned: 1037, captured: 1560")

SNAPSHOTS = {
    "2024-01-01": [
        row("Russia", "All Types", 999), row("Russia", SUMMARY, 500),
        row("Russia", "Tanks", 100), row("Russia", "Infantry Fighting Vehicles", 200),
        row("Russia", "Armoured Personnel Carriers", 50), row("Russia", "Radars", 10),
        row("Ukraine", "All Types", 999),
        row("Ukraine", "Tanks", 20), row("Ukraine", "Infantry Fighting Vehicles", 40),
    ],
    "2024-02-02": [   # the 1st was missing, so the 2nd stands in for the month start
        row("Russia", "All Types", 999), row("Russia", SUMMARY, 600),
        row("Russia", "Tanks", 130), row("Russia", "Infantry Fighting Vehicles", 260),
        row("Russia", "Armoured Personnel Carriers", 50), row("Russia", "Radars", 8),
        row("Ukraine", "Tanks", 20), row("Ukraine", "Infantry Fighting Vehicles", 50),
    ],
    "2024-03-01": [
        row("Russia", "Tanks", 140), row("Russia", "Infantry Fighting Vehicles", 280),
        row("Russia", "Armoured Personnel Carriers", 55), row("Russia", "Radars", 9),
        row("Ukraine", "Tanks", 25), row("Ukraine", "Infantry Fighting Vehicles", 50),
    ],
    "2024-03-20": [   # latest snapshot closes the last (partial) month
        row("Russia", "Tanks", 146, destroyed=100, damaged=6, abandoned=10, captured=30),
        row("Russia", "Infantry Fighting Vehicles", 290, destroyed=290),
        row("Russia", "Armoured Personnel Carriers", 55, destroyed=55),
        row("Russia", "Radars", 9, damaged=9),
        row("Russia", "All Types", 500, destroyed=445),
        row("Ukraine", "Tanks", 27, destroyed=27),
        row("Ukraine", "Infantry Fighting Vehicles", 50, captured=50),
    ],
}


def test_equipment_class_mapping():
    cls = oryx_daily.equipment_class
    assert cls("Tanks") == "tank"
    assert cls("Infantry Fighting Vehicles") == "afv"
    assert cls("Mine-Resistant Ambush Protected") == "afv"
    assert cls("Towed Artillery") == cls("Heavy Mortars") == "artillery"
    assert cls("Multiple Rocket Launchers") == cls("Rocket and Missile Artillery") == "mrl"
    assert cls("Surface-To-Air Missile Systems\n") == "air_defense"   # stray line break in the files
    assert cls("Radars And Communications Equipment") == "ew_radar"
    assert cls("Reconnaissance Unmanned Aerial Vehicles") == "uav"
    assert cls("Naval Ships and Submarines") == "naval"
    assert cls("Trucks and similar vehicles") == cls("Trucks, Vehicles, Jeeps, and Trains") == "vehicles"
    assert cls("Unmanned Ground Vehicles") == "ugv"
    assert cls("Something Oryx adds next year") == "other"
    for total in ("All Types", SUMMARY, "", None,
                  "Losses excluding Recon Drones, UGVs, and Trucks - 18985, of which: destroyed: 1"):
        assert cls(total) is None
    assert set(oryx_daily.TYPE_CLASS.values()) <= set(taxonomy()["equipment_classes"])


def test_parse_csv_handles_quoted_line_breaks():
    text = ('"","country","equipment_type","destroyed","abandoned","captured","damaged","type_total","row_id","Date"\n'
            '"1","Ukraine","Surface-To-Air Missile Systems\n",152,1,6,20,179,18,"2026-11-10"\n')
    (r,) = oryx_daily.parse_csv(text)
    assert oryx_daily.class_totals([r]) == {("UA", "air_defense"): 179}


def test_monthly_differences_clamp_and_skip_totals():
    rows = {(r["month"], r["side"], r["equipment_class"]): r for r in oryx_daily.monthly(SNAPSHOTS)}
    assert {k[0] for k in rows} == {"2024-01", "2024-02", "2024-03"}
    assert {k[2] for k in rows} == {"tank", "afv", "ew_radar"}       # no total or summary rows
    assert rows[("2024-01", "RU", "tank")] == {"month": "2024-01", "side": "RU", "equipment_class": "tank",
                                               "cumulative": 130, "lost_in_month": 30}
    assert rows[("2024-01", "RU", "afv")]["lost_in_month"] == 60     # IFV + APC, summary row ignored
    assert rows[("2024-01", "RU", "afv")]["cumulative"] == 310
    # correction: radars fell from 10 to 8 -> zero losses, true cumulative kept
    assert rows[("2024-01", "RU", "ew_radar")]["lost_in_month"] == 0
    assert rows[("2024-01", "RU", "ew_radar")]["cumulative"] == 8
    assert rows[("2024-02", "RU", "ew_radar")]["lost_in_month"] == 1
    assert rows[("2024-01", "UA", "tank")]["lost_in_month"] == 0
    assert rows[("2024-02", "UA", "tank")]["lost_in_month"] == 5
    # last month is partial: latest snapshot minus the month-start snapshot
    assert rows[("2024-03", "RU", "tank")]["lost_in_month"] == 6
    assert rows[("2024-03", "UA", "afv")]["lost_in_month"] == 0


def test_monthly_needs_two_snapshots():
    assert oryx_daily.monthly({"2024-01-01": SNAPSHOTS["2024-01-01"]}) == []
    assert oryx_daily.monthly({}) == []


def test_ratio_monthly_and_zero_denominators():
    jan, feb, mar = oryx_daily.ratio_monthly(oryx_daily.monthly(SNAPSHOTS))
    assert (jan["ru_tank"], jan["ua_tank"], jan["ru_afv"], jan["ua_afv"]) == (30, 0, 60, 10)
    assert (jan["ru_all"], jan["ua_all"]) == (90, 10)
    assert jan["ru_per_ua_tank"] is None            # Ukraine lost no tanks: no ratio
    assert jan["ru_per_ua_afv"] == 6.0
    assert jan["ru_per_ua_all"] == 9.0
    assert jan["ru_per_ua_all_3m"] is None and feb["ru_per_ua_all_3m"] is None
    assert (feb["ru_tank"], feb["ua_tank"], feb["ru_per_ua_tank"]) == (10, 5, 2.0)
    assert feb["ru_per_ua_afv"] is None
    assert (feb["ru_all"], feb["ua_all"]) == (36, 5)
    assert (mar["ru_all"], mar["ua_all"]) == (16, 2)
    assert mar["ru_per_ua_all_3m"] == round((90 + 36 + 16) / (10 + 5 + 2), 2)
    assert jan["ru_artillery"] == jan["ua_artillery"] == 0
    assert list(jan) == ["month", "ru_tank", "ua_tank", "ru_afv", "ua_afv", "ru_artillery", "ua_artillery",
                         "ru_all", "ua_all", "ru_per_ua_tank", "ru_per_ua_afv", "ru_per_ua_all",
                         "ru_per_ua_all_3m"]


def test_ratio_3m_none_when_no_ukrainian_losses():
    rows = [{"month": m, "side": "RU", "equipment_class": "tank", "cumulative": 0, "lost_in_month": 4}
            for m in ("2024-01", "2024-02", "2024-03")]
    assert [r["ru_per_ua_all_3m"] for r in oryx_daily.ratio_monthly(rows)] == [None, None, None]


def test_latest_totals():
    rows = {(r["side"], r["equipment_class"]): r for r in oryx_daily.latest_totals(SNAPSHOTS)}
    assert set(rows) == {("RU", "tank"), ("RU", "afv"), ("RU", "ew_radar"), ("UA", "tank"), ("UA", "afv")}
    assert rows[("RU", "tank")] == {"as_of": "2024-03-20", "side": "RU", "equipment_class": "tank",
                                    "destroyed": 100, "damaged": 6, "abandoned": 10, "captured": 30,
                                    "total": 146}
    assert rows[("RU", "afv")]["total"] == 345 and rows[("RU", "afv")]["destroyed"] == 345
    assert rows[("UA", "afv")]["captured"] == 50
    assert oryx_daily.latest_totals({}) == []


def test_run_uses_cache_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(oryx_daily, "CACHE", tmp_path)
    header = "country,equipment_type,destroyed,abandoned,captured,damaged,type_total\n"
    (tmp_path / "2024-01-01.csv").write_text(header + "Russia,Tanks,1,0,0,0,1\nUkraine,Tanks,1,0,0,0,1\n")
    (tmp_path / "2024-02-01.csv").write_text(header + "Russia,Tanks,5,0,0,0,5\nUkraine,Tanks,3,0,0,0,3\n")

    def no_network(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(oryx_daily.requests.Session, "get", no_network)
    out = oryx_daily.run(refresh=False)
    assert set(out) == {"oryx_monthly.csv", "oryx_ratio_monthly.csv", "oryx_latest.csv"}
    assert out["oryx_ratio_monthly.csv"][0]["ru_per_ua_tank"] == 2.0


def test_fetch_month_starts_caches_and_falls_back(tmp_path, monkeypatch):
    from datetime import date
    monkeypatch.setattr(oryx_daily, "CACHE", tmp_path)
    monkeypatch.setattr(oryx_daily, "FIRST_MONTH", (2024, 2))
    body = "country,equipment_type,destroyed,abandoned,captured,damaged,type_total\nRussia,Tanks,1,0,0,0,1\n"
    available = {"2022-02-24", "2024-02-03", "2024-03-01", "2024-03-08"}
    calls = []

    class Session:
        headers = {}

        def get(self, url, timeout=None):
            day = url.rsplit("/", 1)[1][:-4]
            calls.append(day)
            ok = day in available
            return type("R", (), {"status_code": 200 if ok else 404, "text": body if ok else "",
                                  "raise_for_status": lambda self: None})()

    snaps = oryx_daily.fetch_month_starts(date(2024, 3, 10), session=Session(), pause=0)
    assert sorted(snaps) == ["2022-02-24", "2024-02-03", "2024-03-01", "2024-03-08"]
    assert calls == ["2022-02-24", "2024-02-01", "2024-02-02", "2024-02-03", "2024-03-01",
                     "2024-03-10", "2024-03-09", "2024-03-08"]
    calls.clear()
    again = oryx_daily.fetch_month_starts(date(2024, 3, 10), session=Session(), pause=0)
    assert sorted(again) == sorted(snaps)
    assert calls == ["2024-03-10", "2024-03-09", "2024-03-08"]     # only the latest probe

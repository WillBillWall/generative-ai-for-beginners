from datetime import date, timedelta

from ingest import warfires


def raw(day, war="", ua="", ru="", cloud="0.4", avg="1.5"):
    return {
        "date": day, "cloud_cover_in_country": "0.9", "cloud_cover_in_east_of_country": cloud,
        "fires_per_day": "50", "war_fires_per_day": war,
        "war_fires_per_day_in_ukraine_held_area": ua, "war_fires_per_day_in_russia_held_area": ru,
        "war_fires_per_day_7dma": avg, "war_fires_per_day_non_cloud_days_7dma": "NA",
    }


def day_rows(start, n, war=4, ua=1, ru=3):
    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "war_fires": war,
             "war_fires_ua_held": ua, "war_fires_ru_held": ru} for i in range(n)]


def test_daily_tidies_sorts_and_drops_partial_today():
    rows = [  # newest first, as published
        raw("2025-03-03", "0", "0", "0"),
        raw("2025-03-02", "7", "3", "4", cloud="NA", avg="NA"),
        raw("2025-03-01", "10", "4", "6", cloud="0.25", avg="8.3333333"),
    ]
    out = warfires.daily(rows, today=date(2025, 3, 3))
    assert [r["date"] for r in out] == ["2025-03-01", "2025-03-02"]      # today dropped
    assert out[0] == {"date": "2025-03-01", "war_fires": 10, "war_fires_ua_held": 4,
                      "war_fires_ru_held": 6, "cloud_cover": 0.25, "war_fires_7d": 8.3}
    assert isinstance(out[0]["war_fires"], int)
    assert out[1]["cloud_cover"] is None and out[1]["war_fires_7d"] is None   # NA -> None
    # a finished day is kept
    assert len(warfires.daily(rows, today=date(2025, 3, 4))) == 3


def test_daily_drops_last_day_with_blanks_but_keeps_earlier_gaps():
    rows = [raw("2025-03-01", "5", "2", "3"), raw("2025-03-02", "", "", ""),
            raw("2025-03-03", "6", "1", "5"), raw("2025-03-04", "2", "", "")]
    out = warfires.daily(rows, today=date(2025, 6, 1))
    assert [r["date"] for r in out] == ["2025-03-01", "2025-03-02", "2025-03-03"]
    assert out[1]["war_fires"] is None and out[1]["war_fires_ua_held"] is None


def test_daily_without_cloud_column():
    rows = [{"date": "2025-03-01", "war_fires_per_day": "3",
             "war_fires_per_day_in_ukraine_held_area": "1",
             "war_fires_per_day_in_russia_held_area": "2"}]
    (row,) = warfires.daily(rows, today=date(2025, 6, 1))
    assert "cloud_cover" not in row and row["war_fires_7d"] is None


def test_monthly_average_share_and_complete():
    days = day_rows("2024-02-01", 29, war=4, ua=1, ru=3)             # leap February, full
    days += day_rows("2024-03-01", 10, war=0, ua=0, ru=0)            # part month, no fires
    days += [{"date": "2024-04-01", "war_fires": 10, "war_fires_ua_held": 10, "war_fires_ru_held": 0},
             {"date": "2024-04-02", "war_fires": None, "war_fires_ua_held": None, "war_fires_ru_held": None},
             {"date": "2024-04-03", "war_fires": 20, "war_fires_ua_held": 5, "war_fires_ru_held": 15}]
    feb, mar, apr = warfires.monthly(days)
    assert feb == {"month": "2024-02", "days": 29, "complete": True, "war_fires_per_day": 4.0,
                   "ua_held_per_day": 1.0, "ru_held_per_day": 3.0, "ua_held_share": 0.25}
    assert mar["complete"] is False and mar["war_fires_per_day"] == 0.0
    assert mar["ua_held_share"] is None                              # no fires, no share
    assert apr["days"] == 3 and apr["war_fires_per_day"] == 15.0     # blank day not counted as 0
    assert apr["ua_held_share"] == 0.5
    assert warfires.monthly(day_rows("2023-02-01", 28))[0]["complete"] is True
    assert warfires.monthly(day_rows("2024-02-01", 28))[0]["complete"] is False


def test_seasonal_index_year_over_year():
    def m(month, v, complete=True):
        return {"month": month, "war_fires_per_day": v, "complete": complete}
    rows = [m("2023-07", 200.0), m("2023-08", 0.0), m("2023-09", 50.0), m("2024-07", 150.0),
            m("2024-08", 30.0), m("2024-09", 80.0, complete=False), m("2024-10", 12.0)]
    out = {r["month"]: r for r in warfires.seasonal_index(rows)}
    assert out["2024-07"] == {"month": "2024-07", "war_fires_per_day": 150.0,
                              "same_month_prev_year": 200.0, "yoy_pct": -25.0}
    assert out["2023-07"]["same_month_prev_year"] is None and out["2023-07"]["yoy_pct"] is None
    assert out["2024-08"]["yoy_pct"] is None                         # previous year was zero
    assert out["2024-09"]["same_month_prev_year"] == 50.0
    assert out["2024-09"]["yoy_pct"] is None                         # part month
    assert out["2024-10"]["yoy_pct"] is None                         # no month a year earlier


def test_fetch_uses_cache_without_network(tmp_path, monkeypatch):
    cache = tmp_path / "war_fires_daily.csv"
    cache.write_text("date,war_fires_per_day\n2025-03-01,3\n")
    monkeypatch.setattr(warfires, "CACHE", cache)

    def no_network(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(warfires, "polite_get", no_network)
    assert warfires.fetch() == [{"date": "2025-03-01", "war_fires_per_day": "3"}]

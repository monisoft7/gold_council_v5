import pandas as pd

import build_economic_calendar


def test_update_snapshot_filters_and_preserves_polls(tmp_path, monkeypatch):
    calls = iter([
        pd.DataFrame([{"country": "USD", "impact": "High", "title": "NFP",
                       "source": "x", "release_time": "2026-09-04T12:30:00Z",
                       "fetched_at": "2026-09-01T10:00:00Z"},
                      {"country": "EUR", "impact": "High", "title": "ECB",
                       "source": "x", "release_time": "2026-09-04T12:30:00Z",
                       "fetched_at": "2026-09-01T10:00:00Z"}]),
        pd.DataFrame([{"country": "USD", "impact": "High", "title": "NFP",
                       "source": "x", "release_time": "2026-09-04T12:30:00Z",
                       "fetched_at": "2026-09-01T10:30:00Z"}]),
    ])
    monkeypatch.setattr(build_economic_calendar, "fetch_weekly_calendar", lambda: next(calls))
    path = tmp_path / "snapshots.csv"
    build_economic_calendar.update_snapshot(path, high_impact_only=True)
    result = build_economic_calendar.update_snapshot(path, high_impact_only=True)
    assert len(result) == 2
    assert set(result["country"]) == {"USD"}
    assert not path.with_suffix(".csv.tmp").exists()

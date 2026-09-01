import pandas as pd

from build_event_history import bls_release_time, build


def test_builds_release_events_from_official_files(tmp_path):
    row = {"released_at": "2020-02-07T00:00:00Z"}
    pd.DataFrame([row]).to_csv(tmp_path / "fred_cpi.csv", index=False)
    pd.DataFrame([row]).to_csv(tmp_path / "fred_payrolls.csv", index=False)
    result = build(str(tmp_path), existing=None)
    assert set(result["section"]) == {"CPI", "NFP"}
    # فبراير شتاء نيويورك: 08:30 ET = 13:30 UTC.
    assert all(result["time"].dt.hour == 13)
    assert all(result["time"].dt.minute == 30)


def test_bls_release_time_respects_new_york_dst():
    assert bls_release_time("2026-01-09").hour == 13
    assert bls_release_time("2026-07-03").hour == 12

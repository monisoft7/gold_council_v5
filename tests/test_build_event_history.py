import pandas as pd

from build_event_history import build


def test_builds_release_events_from_official_files(tmp_path):
    row = {"released_at": "2020-02-07T00:00:00Z"}
    pd.DataFrame([row]).to_csv(tmp_path / "fred_cpi.csv", index=False)
    pd.DataFrame([row]).to_csv(tmp_path / "fred_payrolls.csv", index=False)
    result = build(str(tmp_path), existing=None)
    assert set(result["section"]) == {"CPI", "NFP"}
    assert all(result["time"].dt.hour == 12)
    assert all(result["time"].dt.minute == 30)

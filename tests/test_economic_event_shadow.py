import pandas as pd

from economic_event_shadow import completed_nfp_signals, latest_states


def test_shadow_uses_only_main_nfp_actual_known_by_asof():
    history = pd.DataFrame([
        {"release_time": "2026-09-04T12:30:00Z", "title": "Non-Farm Employment Change",
         "actual_available_at": "2026-09-04T12:30:10Z", "fetched_at": "2026-09-04T12:30:10Z",
         "actual": "70K", "forecast": "50K", "gold_score": -80},
        {"release_time": "2026-09-04T12:30:00Z", "title": "Unemployment Rate",
         "actual_available_at": "2026-09-04T12:30:10Z", "fetched_at": "2026-09-04T12:30:10Z",
         "actual": "4.2%", "forecast": "4.1%", "gold_score": 70},
        {"release_time": "2026-10-02T12:30:00Z", "title": "Non-Farm Employment Change",
         "actual_available_at": "2026-10-02T12:30:10Z", "fetched_at": "2026-10-02T12:30:10Z",
         "actual": "80K", "forecast": "50K", "gold_score": -80},
    ])
    result = completed_nfp_signals(history, as_of="2026-09-04T12:31:00Z")
    assert len(result) == 1
    assert result.iloc[0]["signal"] == -1


def test_latest_journal_record_is_the_current_state():
    rows = [
        {"event_id": "NFP:x", "status": "pending"},
        {"event_id": "NFP:x", "status": "open"},
    ]
    assert latest_states(rows)["NFP:x"]["status"] == "open"

import pandas as pd

from import_global_economic_calendar import import_calendar


def test_import_filters_and_documents_availability_assumption():
    raw = pd.DataFrame([
        {"date": "10/01/2025", "time": "13:30", "currency": "USD",
         "importance": "high", "event": "Nonfarm Payrolls  (Dec)",
         "actual": "256K", "forecast": "164K", "previous": "261K"},
        {"date": "10/01/2025", "time": "13:30", "currency": "EUR",
         "importance": "high", "event": "CPI (MoM)",
         "actual": "1%", "forecast": "1%", "previous": "1%"},
    ])
    out = import_calendar(raw, start="2025-01-01", end="2025-02-01")
    assert len(out) == 1
    assert out.iloc[0]["event_type"] == "NFP"
    assert out.iloc[0]["gold_score"] < 0
    assert "no_capture_timestamp" in out.iloc[0]["availability_assumption"]
    assert out.iloc[0]["source_time_delta_minutes"] == 0

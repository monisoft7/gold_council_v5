import pandas as pd

import news_event_audit as nea


def test_entry_is_strictly_after_event_and_horizons_are_forward():
    events = pd.DataFrame([{
        "available_at": "2024-01-01T20:00:00Z", "gold_impact": "bullish",
        "confidence": 80,
    }])
    prices = pd.DataFrame([
        {"time": "2024-01-01T05:00:00Z", "open": 100, "close": 110},
        {"time": "2024-01-02T05:00:00Z", "open": 110, "close": 111},
        {"time": "2024-01-03T05:00:00Z", "open": 111, "close": 109},
        {"time": "2024-01-04T05:00:00Z", "open": 109, "close": 115},
    ])
    detail, summary = nea.audit(events, prices)
    assert detail.iloc[0]["entry_time"].startswith("2024-01-02")
    assert detail.iloc[0]["entry"] == 110
    assert detail.iloc[0]["correct_1s"] == 1
    assert detail.iloc[0]["correct_3s"] == 1
    assert summary["signals"] == 1


def test_all_neutral_events_produce_zero_signal_report():
    events = pd.DataFrame([{
        "available_at": "2024-01-01T20:00:00Z", "gold_impact": "neutral",
        "confidence": 90,
    }])
    prices = pd.DataFrame([{
        "time": "2024-01-02T05:00:00Z", "open": 100, "close": 101,
    }])
    detail, summary = nea.audit(events, prices)
    assert detail.empty
    assert summary["signals"] == 0
    assert summary["horizons"]["1"]["directional_accuracy_pct"] is None

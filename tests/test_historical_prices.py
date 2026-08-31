import pandas as pd

from historical_prices import audit


def test_price_audit_detects_impossible_candle():
    frame = pd.DataFrame({
        "time": ["2026-01-01", "2026-01-02"],
        "open": [100, 100], "high": [101, 98],
        "low": [99, 99], "close": [100, 100],
    })
    assert audit(frame)["invalid_ohlc"] == 1

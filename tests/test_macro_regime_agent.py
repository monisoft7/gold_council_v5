import pandas as pd

from macro_regime_agent import macro_regime_agent


def test_falling_real_yields_and_dollar_are_bullish_for_gold():
    dates = pd.date_range("2026-01-01", periods=20, tz="UTC")
    frame = pd.DataFrame({
        "available_at": dates,
        "real_yield_10y_value": [2.0 - i * 0.03 for i in range(20)],
        "broad_dollar_value": [110 - i * 0.2 for i in range(20)],
        "vix_value": [15 + i * 0.1 for i in range(20)],
        "cpi_value": 320.0, "fed_funds_value": 4.0,
    })
    report = macro_regime_agent(frame, as_of=dates[-1])
    assert report.score > 25
    assert "شراء" in report.verdict


def test_future_macro_rows_are_ignored():
    dates = pd.date_range("2026-01-01", periods=20, tz="UTC")
    frame = pd.DataFrame({
        "available_at": dates,
        "real_yield_10y_value": list(range(20)),
        "broad_dollar_value": list(range(20)),
        "vix_value": list(range(20)),
    })
    a = macro_regime_agent(frame, as_of=dates[14])
    changed = frame.copy()
    changed.loc[15:, ["real_yield_10y_value", "broad_dollar_value"]] = -999
    b = macro_regime_agent(changed, as_of=dates[14])
    assert a.score == b.score

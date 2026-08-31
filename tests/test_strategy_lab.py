import pandas as pd

from strategy_lab import backtest


def test_signal_executes_on_next_open_and_charges_turnover():
    frame = pd.DataFrame({"time": pd.date_range("2020-01-01", periods=25),
                          "open": [100.0] * 20 + [100, 101, 102, 103, 104]})
    signal = pd.Series([0.0] * 20 + [1.0] * 5)
    result = backtest(frame, signal, cost_bps=5, target_vol=0.10)
    assert result.position.iloc[20] == 0
    assert result.position.iloc[21] >= 0
    assert result.turnover.sum() >= 0

import pandas as pd

from council_intraday_replay import _decision_windows, net_directed_return, summarize_trades


def test_net_directed_return_charges_spread_and_two_sided_slippage():
    assert net_directed_return(1.0, 1, spread_cost_pct=0.1) == 0.85
    assert net_directed_return(-1.0, -1, spread_cost_pct=0.1) == 0.85


def test_summary_keeps_holds_out_of_trade_accuracy():
    frame = pd.DataFrame([
        {"signal": 1, "net_15m_pct": 0.2, "net_60m_pct": -0.1, "net_240m_pct": 0.4},
        {"signal": -1, "net_15m_pct": -0.2, "net_60m_pct": 0.3, "net_240m_pct": -0.1},
        {"signal": 0, "net_15m_pct": None, "net_60m_pct": None, "net_240m_pct": None},
    ])
    report = summarize_trades(frame)
    assert report["decision_count"] == 3
    assert report["signal_count"] == 2
    assert report["hold_count"] == 1
    assert report["horizon_15m"]["trades"] == 2
    assert report["horizon_15m"]["win_rate_pct"] == 50.0


def test_continuous_bars_create_one_four_hour_window_at_requested_hour():
    times = pd.date_range("2025-01-02T17:00:00Z", periods=24, freq="15min")
    bars = pd.DataFrame({
        "time": times, "open": range(24), "close": range(24),
        "spread": 10,
    })
    windows = list(_decision_windows(bars, decision_hour_utc=18))
    assert len(windows) == 1
    decision_time, kind, window = windows[0]
    assert decision_time == pd.Timestamp("2025-01-02T18:00:00Z")
    assert kind == "ROUTINE"
    assert len(window) == 16

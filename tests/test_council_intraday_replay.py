import pandas as pd

from council_intraday_replay import (
    _decision_windows,
    net_directed_return,
    simulate_live_exit,
    summarize_trades,
)


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


def _execution_window(highs, lows, closes=None, spread=10):
    count = len(highs)
    closes = closes or [100.0] * count
    return pd.DataFrame({
        "time": pd.date_range("2026-01-02T18:00:00Z", periods=count, freq="15min"),
        "open": [100.0] * count,
        "high": highs,
        "low": lows,
        "close": closes,
        "spread": spread,
        "phase": "after",
    })


def _long_decision():
    return {
        "signal": 1,
        "levels": {"entry": 100.0, "sl": 98.0, "tp1": 102.0},
    }


def test_live_exit_uses_ask_entry_and_tp1_before_four_hours():
    window = _execution_window([101.0, 102.2], [99.0, 100.0])
    result = simulate_live_exit(window, _long_decision(), slippage_bps_per_side=0)
    assert result["exit_reason"] == "tp1"
    assert result["entry_price"] == 100.1
    assert result["exit_price"] == 102.1
    assert result["net_return_pct"] == round((102.1 / 100.1 - 1) * 100, 6)


def test_live_exit_chooses_conservative_stop_when_same_bar_hits_both():
    window = _execution_window([102.5], [97.5])
    result = simulate_live_exit(window, _long_decision(), slippage_bps_per_side=0)
    assert result["exit_reason"] == "sl"
    assert result["exit_price"] == 98.1


def test_live_exit_uses_last_bid_close_at_four_hour_timeout():
    window = _execution_window(
        [101.0] * 16, [99.0] * 16, closes=[100.0] * 15 + [101.0]
    )
    result = simulate_live_exit(window, _long_decision(), slippage_bps_per_side=0)
    assert result["exit_reason"] == "time_4h"
    assert result["exit_price"] == 101.0


def test_summary_reports_live_execution_separately_from_mark_to_market():
    frame = pd.DataFrame([
        {"signal": 1, "net_15m_pct": 0.1, "net_60m_pct": 0.1,
         "net_240m_pct": -0.2, "execution_net_240m_pct": 0.3,
         "execution_exit_reason": "tp1"},
        {"signal": 1, "net_15m_pct": -0.1, "net_60m_pct": -0.1,
         "net_240m_pct": 0.2, "execution_net_240m_pct": -0.1,
         "execution_exit_reason": "sl"},
    ])
    report = summarize_trades(frame)
    assert report["execution_240m"]["trades"] == 2
    assert report["execution_240m"]["profit_factor"] == 3.0
    assert report["execution_240m"]["exit_reasons"] == {"tp1": 1, "sl": 1}

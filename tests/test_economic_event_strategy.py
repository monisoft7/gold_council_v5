from types import SimpleNamespace

import pandas as pd
import pytest

from economic_event_strategy import (
    EventStrategyConfig,
    aggregate_event_signals,
    pre_event_atr,
    run_strategy,
    summarize,
    simulate_event,
)


def _window(direction_move=1.0):
    times = pd.date_range("2025-01-10T09:45:00Z", periods=33, freq="15min")
    rows = []
    for index, time in enumerate(times):
        before = index < 16
        base = 100.0 if before else 100.0 + direction_move * (index - 15) * 0.2
        rows.append({"time": time, "open": base, "high": base + 0.2,
                     "low": base - 0.2, "close": base + 0.1,
                     "spread": 2, "phase": "before" if before else "after",
                     "event_time": "2025-01-10T13:45:00Z", "event_type": "NFP"})
    return pd.DataFrame(rows)


def test_cpi_conflict_is_explicit_and_not_averaged_away():
    values = pd.DataFrame([
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI",
         "title": "CPI", "gold_score": 80, "availability_assumption": "x"},
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI",
         "title": "Core CPI", "gold_score": -40, "availability_assumption": "x"},
    ])
    result = aggregate_event_signals(values)
    assert result.iloc[0]["component_conflict"]


def test_atr_uses_only_pre_event_bars():
    window = _window()
    original = pre_event_atr(window)
    window.loc[window.phase == "after", "high"] = 1000
    assert pre_event_atr(window) == original


def test_stop_is_conservative_and_costs_are_charged():
    window = _window()
    signal = SimpleNamespace(signal=1, event_time=pd.Timestamp("2025-01-10T13:45:00Z"),
                             event_type="NFP", gold_score=80,
                             component_count=1, component_conflict=False)
    config = EventStrategyConfig(sl_atr_mult=1.0)
    # أجبر أول شمعة بعد الخبر على ضرب الوقف.
    window.loc[window.phase == "after", "low"] = 90
    trade = simulate_event(window, signal, config)
    assert trade["exit_reason"] == "atr_stop"
    assert trade["r_multiple"] == pytest.approx(-1.0)
    assert trade["roundtrip_cost_price"] > 0


def test_conflicted_event_is_skipped_by_default():
    surprises = pd.DataFrame([
        {"release_time": "2025-01-10T13:45:00Z", "event_type": "NFP",
         "title": "A", "gold_score": 80, "availability_assumption": "x"},
        {"release_time": "2025-01-10T13:45:00Z", "event_type": "NFP",
         "title": "B", "gold_score": -20, "availability_assumption": "x"},
    ])
    bars = _window()
    trades = run_strategy(surprises, bars, EventStrategyConfig())
    assert trades.empty


def test_subset_summary_rebuilds_its_own_equity_curve():
    trades = pd.DataFrame({
        "pnl_usd": [100.0, -50.0], "equity_after": [20_100.0, 20_050.0],
        "net_return_pct": [1.0, -0.5], "r_multiple": [1.0, -0.5],
        "exit_reason": ["time_exit", "atr_stop"],
    })
    result = summarize(trades, starting_equity=10_000)
    assert result["total_return_pct"] == 0.5

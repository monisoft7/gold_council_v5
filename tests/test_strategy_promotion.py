import pandas as pd

from strategy_promotion import evaluate_promotion


def _report(trades, pf, mean=0.1):
    return {
        "strategy_profile": "intraday_4h",
        "cost_model": {"observed_mt5_spread": True},
        "execution_240m": {
            "trades": trades,
            "profit_factor": pf,
            "mean_net_return_pct": mean,
        },
    }


def _diverse_forward_decisions():
    dates = pd.date_range("2025-01-02", periods=20, freq="15D", tz="UTC")
    return pd.DataFrame({
        "decision_time": dates,
        "signal": 1,
        "execution_net_240m_pct": [0.1] * len(dates),
    })


def test_promotion_passes_only_with_three_profitable_diverse_periods():
    result = evaluate_promotion(
        _report(45, 1.2), _report(25, 1.3), _report(20, 1.4),
        _diverse_forward_decisions(),
    )
    assert result["promotion_allowed"] is True
    assert result["failed_checks"] == []


def test_promotion_blocks_small_clustered_negative_forward_sample():
    decisions = pd.DataFrame({
        "decision_time": pd.date_range("2026-08-21", periods=7, freq="D", tz="UTC"),
        "signal": 1,
        "execution_net_240m_pct": [-0.1] * 7,
    })
    result = evaluate_promotion(
        _report(42, 1.09), _report(10, 1.5), _report(7, 0.37, mean=-0.3),
        decisions,
    )
    assert result["promotion_allowed"] is False
    assert "forward_sample" in result["failed_checks"]
    assert "forward_profit_factor" in result["failed_checks"]
    assert "forward_cluster_concentration" in result["failed_checks"]


def test_promotion_fails_closed_without_live_execution_metrics():
    result = evaluate_promotion({}, {}, {}, pd.DataFrame())
    assert result["promotion_allowed"] is False
    assert "live_execution_metric_in_all_periods" in result["failed_checks"]

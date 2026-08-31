from types import SimpleNamespace

from agent_ablation import metrics


def test_ablation_metrics_split_by_trade_date():
    trades = [
        SimpleNamespace(day="2018-01-01", pnl_pct=2.0, stop_hit=False),
        SimpleNamespace(day="2024-01-01", pnl_pct=-1.0, stop_hit=True),
    ]
    result = metrics(trades, "2023-01-01", "2026-12-31")
    assert result["trades"] == 1
    assert result["sum_pnl_pct"] == -1.0
    assert result["stop_rate_pct"] == 100.0

import pandas as pd

import baselines


def test_strategy_signal_is_shifted_before_returns(monkeypatch):
    frame = pd.DataFrame({
        "open": [100, 100, 200], "high": [101, 201, 201],
        "low": [99, 99, 199], "close": [100, 200, 200],
    })
    monkeypatch.setattr(baselines, "signals", lambda df: {
        "test": pd.Series([0.0, 1.0, 1.0])
    })
    result = baselines.evaluate(frame, cost_bps=0)["test"]
    # القفزة 100% حدثت قبل أن تصبح إشارة الصف الثاني قابلة للتنفيذ.
    assert result["total_return_pct"] == 0.0

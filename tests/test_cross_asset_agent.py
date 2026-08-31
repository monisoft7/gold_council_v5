import numpy as np
import pandas as pd

from cross_asset_agent import cross_asset_from_history


def test_zero_crossing_yield_does_not_create_infinite_signal():
    dates = pd.date_range("2020-01-01", periods=30, tz="UTC")
    gold = pd.DataFrame({"time": dates, "close": np.linspace(1500, 1550, 30)})
    macro = pd.DataFrame({
        "available_at": dates,
        "dxy": np.linspace(100, 98, 30),
        "us10y": np.linspace(-0.1, 0.1, 30),
        "vix": np.linspace(20, 22, 30),
    })
    report = cross_asset_from_history(gold, macro, as_of=dates[-1])
    assert np.isfinite(report.score)
    assert any("نقطة أساس" in bullet for bullet in report.bullets)

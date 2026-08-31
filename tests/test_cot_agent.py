import pandas as pd

from cot_agent import cot_positioning_agent


def test_rising_noncommercial_net_is_bullish():
    dates = pd.date_range("2025-01-03", periods=20, freq="7D", tz="UTC")
    frame = pd.DataFrame({
        "cot_available_at": dates,
        "cot_noncommercial_net": [100000 + i * 10000 for i in range(20)],
        "cot_open_interest": 500000,
    })
    report = cot_positioning_agent(frame, as_of=dates[-1])
    assert report.score > 0


def test_future_cot_report_is_ignored():
    dates = pd.date_range("2025-01-03", periods=12, freq="7D", tz="UTC")
    frame = pd.DataFrame({
        "cot_available_at": dates,
        "cot_noncommercial_net": list(range(12)),
        "cot_open_interest": 100,
    })
    cutoff = dates[9]
    a = cot_positioning_agent(frame, as_of=cutoff)
    frame.loc[10:, "cot_noncommercial_net"] = 999999
    b = cot_positioning_agent(frame, as_of=cutoff)
    assert a.score == b.score

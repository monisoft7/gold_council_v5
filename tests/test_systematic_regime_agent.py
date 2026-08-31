import numpy as np
import pandas as pd

import council
from agents import AgentReport
from systematic_regime_agent import systematic_regime_agent


def _vote(key, score):
    return AgentReport(key=key, name=key, icon="", role="", score=score,
                       confidence=80, weight=1.0)


def test_falling_multi_horizon_regime_blocks_long_and_short():
    history = pd.DataFrame({"close": np.linspace(2000, 1000, 300)})
    gate = systematic_regime_agent(history)
    assert gate.flags["block_long"] is True
    assert gate.flags["block_short"] is True
    assert gate.flags["risk_multiplier"] == 0.0


def test_long_flat_gate_vetoes_council_short():
    history = pd.DataFrame({"close": np.linspace(1000, 2000, 300)})
    reports = [_vote("tech", -80), _vote("macro_data", -80),
               _vote("cot", -80), systematic_regime_agent(history)]
    decision = council.chairman_decision(reports, {}, 10, 2000,
                                         trend_bias=-1, ema200=2100)
    assert decision["signal"] == 0
    assert "long/flat" in decision["vetoed"]

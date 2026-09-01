import numpy as np
import pandas as pd

import chronos_foundation_agent as cfa


class FakePipeline:
    def predict_quantiles(self, inputs, prediction_length, quantile_levels):
        last = float(inputs[0][-1])
        q = np.zeros((1, prediction_length, 3), dtype=float)
        q[:, :, 0] = last * 0.99
        q[:, :, 1] = last * 1.02
        q[:, :, 2] = last * 1.04
        median = np.full((1, prediction_length), last * 1.02)
        return q, median


def test_foundation_agent_is_experimental_and_non_voting():
    frame = pd.DataFrame({"close": np.linspace(100, 130, 100)})
    report = cfa.chronos_foundation_agent(frame, pipeline=FakePipeline())
    assert report.score > 0
    assert report.weight == 0
    assert report.flags["experimental"] is True
    assert report.flags["vote_eligible"] is False


def test_foundation_agent_fails_closed_on_short_history():
    report = cfa.chronos_foundation_agent(pd.DataFrame({"close": [1, 2, 3]}))
    assert report.score == 0
    assert report.flags["available"] is False

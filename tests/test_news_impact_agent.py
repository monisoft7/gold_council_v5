import pandas as pd

import news_impact_agent as nia


def test_future_event_is_never_visible():
    history = pd.DataFrame([{
        "available_at": "2024-01-02T20:00:00Z", "gold_impact": "bullish",
        "magnitude": 90, "confidence": 90, "horizon_hours": 24,
        "rationale": "future",
    }])
    report = nia.news_impact_agent(history, as_of="2024-01-02T19:59:59Z")
    assert report.score == 0
    assert report.weight == 0


def test_latest_available_event_decays_and_stays_non_voting():
    history = pd.DataFrame([{
        "available_at": "2024-01-02T12:00:00Z", "gold_impact": "bearish",
        "magnitude": 80, "confidence": 50, "horizon_hours": 24,
        "rationale": "real yields rose",
    }])
    report = nia.news_impact_agent(history, as_of="2024-01-02T18:00:00Z")
    assert report.score == -30
    assert report.flags["voting_enabled"] is False

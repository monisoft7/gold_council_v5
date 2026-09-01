import pandas as pd

from numeric_surprise_audit import aggregate_surprises, evaluate


def test_cpi_components_become_one_event_and_no_duplicate_vote():
    surprises = pd.DataFrame([
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI",
         "title": "CPI (MoM)", "gold_score": -50, "source": "x",
         "availability_assumption": "test"},
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI",
         "title": "Core CPI (MoM)", "gold_score": 20, "source": "x",
         "availability_assumption": "test"},
    ])
    result = aggregate_surprises(surprises)
    assert len(result) == 1
    assert result.iloc[0]["gold_score"] == -15
    assert result.iloc[0]["signal"] == -1


def test_audit_scores_only_directional_events():
    surprises = pd.DataFrame([
        {"release_time": "2025-01-10T13:30:00Z", "event_type": "NFP",
         "title": "NFP", "gold_score": -80, "source": "x",
         "availability_assumption": "test"},
        {"release_time": "2025-01-29T19:00:00Z", "event_type": "FOMC",
         "title": "FOMC", "gold_score": 0, "source": "x",
         "availability_assumption": "test"},
    ])
    returns = pd.DataFrame([
        {"event_time": pd.Timestamp("2025-01-10T13:30:00Z"), "event_type": "NFP",
         "return_15m_pct": -0.2, "return_60m_pct": -0.3,
         "return_240m_pct": -0.4, "return_1440m_pct": -0.5},
    ])
    rows, report = evaluate(surprises, returns)
    assert len(rows) == 1
    assert report["directional_events"] == 1
    assert report["by_horizon"]["15"]["accuracy_pct"] == 100.0

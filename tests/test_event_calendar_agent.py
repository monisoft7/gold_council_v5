import pandas as pd

from event_calendar_agent import event_calendar_agent


def test_event_within_24h_blocks_without_directional_vote():
    events = pd.DataFrame({
        "time": ["2026-01-02T13:30:00Z"], "title": ["US CPI Release"],
        "source": ["bls.gov"], "section": ["inflation"],
    })
    report = event_calendar_agent(pd.Timestamp("2026-01-02T04:00:00Z"), events=events)
    assert report.score == 0
    assert report.flags["trade_block"] is True


def test_event_in_three_days_only_reduces_risk():
    events = pd.DataFrame({
        "time": ["2026-01-04T12:00:00Z"], "title": ["NFP payroll release"],
    })
    report = event_calendar_agent(pd.Timestamp("2026-01-02T04:00:00Z"), events=events)
    assert report.flags["trade_block"] is False
    assert report.flags["risk_multiplier"] == 0.5


def test_date_outside_calendar_coverage_is_not_called_safe():
    events = pd.DataFrame({
        "time": ["2026-01-03T13:30:00Z"],
        "title": ["US Nonfarm Payrolls"],
        "source": ["BLS"], "section": ["NFP"],
    })
    report = event_calendar_agent(pd.Timestamp("2015-01-02T04:00:00Z"), events=events)
    assert report.flags["calendar_available"] is False
    assert report.flags["risk_multiplier"] == 0.5
    assert report.verdict == "خارج تغطية التقويم"


def test_one_future_event_family_does_not_mask_stale_families():
    events = pd.DataFrame({
        "time": [
            "2026-08-07T12:30:00Z",
            "2026-08-12T12:30:00Z",
            "2026-09-16T19:00:00Z",
        ],
        "title": ["US Nonfarm Payrolls", "US CPI Release", "FOMC Meeting"],
        "source": ["BLS", "BLS", "Federal Reserve"],
        "section": ["NFP", "CPI", "FOMC"],
    })
    report = event_calendar_agent(pd.Timestamp("2026-08-31T04:00:00Z"), events=events)
    assert report.flags["calendar_available"] is False
    assert set(report.flags["incomplete_kinds"]) == {"CPI", "NFP"}
    assert report.flags["risk_multiplier"] == 0.5
    assert report.verdict == "تغطية جزئية"


def test_far_future_first_event_does_not_claim_historical_coverage():
    events = pd.DataFrame({
        "time": [
            "2008-01-04T12:30:00Z",
            "2008-01-10T12:30:00Z",
            "2023-02-01T19:00:00Z",
        ],
        "title": ["US Nonfarm Payrolls", "US CPI Release", "FOMC Meeting"],
        "section": ["NFP", "CPI", "FOMC"],
    })
    report = event_calendar_agent(pd.Timestamp("2008-01-03T04:00:00Z"), events=events)
    assert report.flags["calendar_available"] is False
    assert "FOMC" in report.flags["incomplete_kinds"]
    assert report.flags["risk_multiplier"] == 0.5

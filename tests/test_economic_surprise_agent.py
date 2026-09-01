from types import SimpleNamespace

import pandas as pd

from economic_surprise_agent import (
    EconomicValue,
    calculate_surprise,
    economic_surprise_agent,
    fetch_weekly_calendar,
    merge_snapshots,
    parse_economic_value,
)


def test_parser_supports_common_calendar_units_and_parentheses():
    assert parse_economic_value("-23K") == EconomicValue(-23_000.0, "K")
    assert parse_economic_value("$1.2B") == EconomicValue(1_200_000_000.0, "B")
    assert parse_economic_value("0.3%") == EconomicValue(0.3, "%")
    assert parse_economic_value("(4.1)") == EconomicValue(-4.1, "number")
    assert parse_economic_value("") is None


def test_event_semantics_change_gold_direction():
    jobs = calculate_surprise("100K", "50K", "25K", "Non-Farm Employment Change")
    unemployment = calculate_surprise("4.3%", "4.1%", "4.0%", "Unemployment Rate")
    assert jobs["gold_score"] < 0
    assert unemployment["gold_score"] > 0


class FakeSession:
    def get(self, *args, **kwargs):
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: [{
                "title": "CPI m/m", "country": "USD", "date": "2026-09-01T08:30:00-04:00",
                "impact": "High", "forecast": "0.3%", "previous": "0.2%",
                "actual": "0.4%",
            }],
        )


def test_fetch_uses_observation_time_not_release_time_for_actual():
    fetched = pd.Timestamp("2026-09-01T12:31:15Z")
    frame = fetch_weekly_calendar(fetched_at=fetched, session=FakeSession())
    assert frame.iloc[0]["release_time"] == pd.Timestamp("2026-09-01T12:30:00Z")
    assert frame.iloc[0]["actual_available_at"] == fetched


def test_snapshot_merge_keeps_what_each_poll_knew():
    first = fetch_weekly_calendar(
        fetched_at="2026-09-01T12:29:00Z", session=FakeSession()
    )
    second = fetch_weekly_calendar(
        fetched_at="2026-09-01T12:31:00Z", session=FakeSession()
    )
    result = merge_snapshots(first, second)
    assert len(result) == 2


def test_agent_cannot_see_actual_collected_after_decision():
    history = fetch_weekly_calendar(
        fetched_at="2026-09-01T12:31:00Z", session=FakeSession()
    )
    before = economic_surprise_agent(history, as_of="2026-09-01T12:30:30Z")
    after = economic_surprise_agent(history, as_of="2026-09-01T12:32:00Z")
    assert before.score == 0
    assert before.flags.get("observations", 0) == 0
    assert after.score < 0
    assert after.flags["non_voting"] is True

import pandas as pd
import pytest

from mt5_event_history import (
    canonical_release_time,
    canonicalize_events,
    event_return_summary,
    extract_event_window,
    load_event_schedule,
)


def _rates(start="2026-03-06T13:00:00Z", periods=40):
    times = pd.date_range(start, periods=periods, freq="5min")
    return pd.DataFrame({
        # Pandas 3 may store DatetimeIndex values at microsecond resolution,
        # while Pandas 2 commonly uses nanoseconds. Convert explicitly to
        # datetime64[s] so this MT5 epoch-seconds fixture is version agnostic.
        "time": times.to_numpy(dtype="datetime64[s]").astype("int64"),
        "open": range(100, 100 + periods), "high": range(101, 101 + periods),
        "low": range(99, 99 + periods), "close": range(100, 100 + periods),
        "tick_volume": 10, "spread": 2, "real_volume": 0,
    }).to_records(index=False)


def test_rate_fixture_uses_epoch_seconds_across_pandas_resolutions():
    rates = _rates(periods=1)
    assert int(rates["time"][0]) == int(pd.Timestamp("2026-03-06T13:00:00Z").timestamp())


def test_dst_aware_release_times_are_not_fixed_utc():
    assert canonical_release_time("2026-01-09", "NFP").hour == 13
    assert canonical_release_time("2026-07-03", "NFP").hour == 12
    assert canonical_release_time("2026-01-28", "FOMC").hour == 19
    assert canonical_release_time("2026-07-29", "FOMC").hour == 18


def test_canonicalization_removes_duplicate_corrupt_event_rows():
    events = pd.DataFrame([
        {"time": "2026-03-06T12:30:00Z", "title": "NFP", "section": "NFP"},
        {"time": "2026-03-06T13:30:00Z", "title": "Nonfarm Payrolls", "section": "x"},
    ])
    result = canonicalize_events(events)
    assert len(result) == 1
    assert result.iloc[0]["event_time"] == pd.Timestamp("2026-03-06T13:30:00Z")


def test_surprise_schema_can_drive_price_collection_directly():
    events = pd.DataFrame([
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI", "title": "CPI"},
        {"release_time": "2025-01-15T13:30:00Z", "event_type": "CPI", "title": "Core CPI"},
    ])
    result = load_event_schedule(events, start="2025-01-01", end="2025-02-01")
    assert len(result) == 1
    assert result.iloc[0]["event_type"] == "CPI"


def test_window_enters_only_at_first_bar_after_non_aligned_release():
    event = pd.Timestamp("2026-03-06T13:32:00Z")
    window = extract_event_window(_rates(), event, 5, bars_before=3, bars_after=4)
    after = window[window["phase"] == "after"]
    before = window[window["phase"] == "before"]
    assert len(before) == 3 and len(after) == 4
    assert after.iloc[0]["time"] == pd.Timestamp("2026-03-06T13:35:00Z")
    assert before["time"].max() < after["time"].min()


def test_event_returns_charge_observed_spread():
    event = pd.Timestamp("2026-03-06T13:30:00Z")
    window = extract_event_window(_rates(), event, 5, bars_before=2, bars_after=10)
    result = event_return_summary(window, timeframe_minutes=5, point=0.01,
                                  horizons_minutes=(15,))
    assert result["status"] == "ok"
    assert result["return_15m_pct"] == pytest.approx(
        (108 / 106 - 1) * 100 - (2 * 0.01 / 106 * 100)
    )
    assert result["spread_cost_pct"] > 0

import pandas as pd
import pytest

from point_in_time import normalize_records, asof_join, news_window, assert_no_future


def test_asof_join_uses_release_time_not_observation_time():
    decisions = pd.DataFrame({"decision_at": ["2026-01-10", "2026-01-12"]})
    raw = pd.DataFrame({
        "period": ["2025-12-01"],
        "release": ["2026-01-11"],
        "value": [3.1],
    })
    facts = normalize_records(raw, observed_col="period", released_col="release")
    out = asof_join(decisions, facts, ["value"], prefix="cpi_", tolerance="60D")
    assert pd.isna(out.iloc[0]["cpi_value"])
    assert out.iloc[1]["cpi_value"] == 3.1
    assert_no_future(out)


def test_invalid_release_order_is_rejected():
    raw = pd.DataFrame({"obs": ["2026-02-01"], "release": ["2026-01-31"]})
    with pytest.raises(ValueError):
        normalize_records(raw, observed_col="obs", released_col="release")


def test_news_window_excludes_future_and_stale_items():
    news = pd.DataFrame({
        "available_at": ["2026-01-01", "2026-01-09", "2026-01-11"],
        "title": ["old", "valid", "future"],
    })
    got = news_window(news, "2026-01-10", hours=72)
    assert got["title"].tolist() == ["valid"]

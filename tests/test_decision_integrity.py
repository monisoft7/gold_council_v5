# -*- coding: utf-8 -*-
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd

import agents
import backtester_v5
import council


def _report(key, score, confidence=70):
    return agents.AgentReport(
        key=key, name=key, icon="", role="", score=score,
        confidence=confidence, weight=0.99,
    )


def test_quality_filter_sets_non_executable_signal():
    reports = [
        _report("macro", 20), _report("tech", 20), _report("event", 0),
        _report("cross", 0), _report("season", 0), _report("pattern", 0),
        _report("expert", 0), _report("risk", 100), _report("scout", 100),
    ]
    dec = council.chairman_decision(
        reports, {}, atr_value=10, last_price=2700,
        trend_bias=0, ema200=0,
    )
    assert dec["signal"] == 0
    assert dec["quality_passed"] is False
    assert dec["levels"]["entry"] is None
    assert "محايد" in dec["decision"]


def test_unvalidated_strategy_cannot_claim_high_confidence():
    reports = [_report("tech", 80, 95), _report("macro_data", 80, 95),
               _report("cot", 80, 95)]
    dec = council.chairman_decision(reports, {}, 10, 2000,
                                    trend_bias=1, ema200=1900)
    assert dec["confidence"] <= 60
    assert dec["research_only"] is True
    assert dec["strategy_validated"] is False


def test_collection_and_risk_agents_do_not_change_direction_score():
    base = [_report("macro", 50), _report("tech", 50)]
    noisy = base + [_report("risk", -100), _report("scout", -100)]
    a = council.chairman_decision(base, {}, 10, 2700)
    b = council.chairman_decision(noisy, {}, 10, 2700)
    assert a["raw_score"] == b["raw_score"]


def test_family_aggregation_caps_correlated_evidence():
    base = [
        _report("macro", 80), _report("tech", -20),
        _report("macro_data", -20), _report("cot", -20),
    ]
    duplicated_news = base + [_report("expert", 80)]
    family_base = council.chairman_decision(base, {}, 10, 2700,
                                             aggregation_mode="family")
    family_duplicate = council.chairman_decision(
        duplicated_news, {}, 10, 2700, aggregation_mode="family"
    )
    legacy_base = council.chairman_decision(base, {}, 10, 2700,
                                             aggregation_mode="agent")
    legacy_duplicate = council.chairman_decision(
        duplicated_news, {}, 10, 2700, aggregation_mode="agent"
    )
    assert family_base["raw_score"] == family_duplicate["raw_score"]
    assert legacy_base["raw_score"] != legacy_duplicate["raw_score"]
    assert family_duplicate["family_scores"]["news"] == 80.0


def test_duplicate_agent_key_cannot_change_family_vote():
    reports = [
        _report("macro", 70, 60), _report("macro", -100, 50),
        _report("tech", 50), _report("macro_data", 50), _report("cot", 50),
    ]
    dec = council.chairman_decision(reports, {}, 10, 2700)
    assert dec["family_scores"]["news"] == 70.0


def test_high_impact_event_blocks_trade_without_voting_sell():
    reports = [
        _report("macro", 90), _report("macro_data", 90),
        _report("tech", 90), _report("cross", 90),
    ]
    event = _report("event", -100)
    event.flags = {"trade_block": True}
    dec = council.chairman_decision(reports + [event], {}, 10, 2700)
    assert dec["signal"] == 0
    assert "بوابة أحداث" in dec["vetoed"]


def test_event_veto_cannot_leak_through_at_exact_threshold():
    reports = [
        _report("macro", 100), _report("macro_data", 100),
        _report("tech", 100), _report("cross", 100),
        _report("season", 100), _report("pattern", 100),
        _report("expert", 100), _report("cot", 100),
    ]
    event = _report("event", 0)
    event.flags = {"trade_block": True, "risk_multiplier": 0.0}
    dec = council.chairman_decision(reports + [event], {}, 10, 2700)
    assert dec["final_score"] == 25.0
    assert dec["signal"] == 0
    assert dec["quality_passed"] is False
    assert dec["levels"]["entry"] is None


def test_event_risk_multiplier_reaches_final_decision():
    reports = [_report("tech", 80), _report("macro_data", 80), _report("cot", 80)]
    event = _report("event", 0)
    event.flags = {"trade_block": False, "risk_multiplier": 0.5}
    dec = council.chairman_decision(reports + [event], {}, 10, 2700)
    assert dec["risk_multiplier"] == 0.5


def test_historical_news_age_uses_decision_time_not_wall_clock():
    published = datetime(2024, 1, 1, tzinfo=timezone.utc)
    as_of = datetime(2024, 1, 1, 3, tzinfo=timezone.utc)
    assert agents._age_hours(published, as_of=as_of) == 3.0


def test_expert_agent_ignores_generic_news_forecasts():
    generic = {"title": "Gold forecast: rally", "source": "Generic Wire"}
    expert = {"title": "Gold forecast: rally", "source": "Kitco News"}
    assert agents.expert_scout([generic]).score == 0
    assert agents.expert_scout([expert]).score > 0


def test_short_cost_is_deducted_for_window_exit():
    full = pd.DataFrame([
        {"time": "2026-01-01", "open": 100, "high": 101, "low": 99, "close": 100},
        {"time": "2026-01-02", "open": 100, "high": 100, "low": 98, "close": 99},
    ])
    trade = backtester_v5.regress_trade(
        full, 0, -1, {"entry": 100, "sl": 110, "tp1": 90}, {},
        max_w=1, cost=0.05,
    )
    assert trade.exit_reason == "window_end"
    assert 0 < trade.pnl_pct < 1.0
    assert trade.exit_price > 99


def test_replay_entry_is_next_session_open(monkeypatch):
    rows = []
    for i in range(230):
        close = 100 + i * 0.1
        rows.append({
            "time": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "open": close + 0.07, "high": close + 1,
            "low": close - 1, "close": close, "volume": 1,
        })
    frame = pd.DataFrame(rows)
    monkeypatch.setattr(backtester_v5, "load_prices_csv", lambda _: frame)

    fake_report = SimpleNamespace(key="tech", score=80, confidence=80)
    def fake_decision(window, news, capital, risk_pct, as_of=None,
                      macro_history=None, events_path="events_3y.csv",
                      aggregation_mode="family"):
        idx = len(window) - 1
        return ({
            "decision": "شراء", "signal": 1, "final_score": 80,
            "confidence": 80, "agreement": 100, "vetoed": None,
        }, {
            "reports": [fake_report], "rsi": 50, "volatility_pct": 1,
            "macd_hist": 1, "trend_bias": 1, "atr": 1,
        })
    monkeypatch.setattr(backtester_v5, "simulate_decision", fake_decision)
    _, trades, _ = backtester_v5.run_replay(
        step_days=100, prices_csv="unused", windows_days_max=7,
    )
    assert trades
    decision_index = 210
    assert trades[0].entry == frame.iloc[decision_index + 1]["open"]


def test_feature_row_preserves_each_agent_for_future_ablation():
    trade = SimpleNamespace(day="2026-01-01", decision="شراء", exit_window_days=5)
    tech = SimpleNamespace(key="tech", score=42, confidence=80, flags={})
    gate = SimpleNamespace(
        key="systematic_gate", score=0, confidence=75,
        flags={"systematic_score": 50},
    )
    dec = {
        "final_score": 30, "confidence": 55, "agreement": 75,
        "vetoed": None, "evidence_coverage": 60, "evidence_quality": 70,
        "supporting_families": ["price", "macro", "flows"],
        "family_scores": {"price": 33.5, "macro": 21.0},
        "risk_multiplier": 0.5,
    }
    row = backtester_v5._to_feature_row(
        trade, dec,
        {"reports": [tech, gate], "rsi": 50, "atr": 10, "macd_hist": 1},
        {},
    )
    assert row["agent_tech_score"] == 42
    assert row["agent_systematic_gate_confidence"] == 75
    assert row["systematic_score"] == 50
    assert row["supporting_family_count"] == 3
    assert row["family_price_score"] == 33.5

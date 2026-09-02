from types import SimpleNamespace
import sys

import decision_pipeline
import paper_journal
import mt5_demo_service
from mt5_demo_service import seconds_until_execution_window, within_execution_window


def test_risk_multiplier_changes_actual_position_size():
    decision = {
        "signal": 1,
        "risk_multiplier": 0.5,
        "levels": {"entry": 100.0, "sl": 90.0},
    }
    decision_pipeline.apply_risk_sizing(decision, capital=10_000, risk_pct=1.0)
    assert decision["base_position_oz"] == 10.0
    assert decision["position_oz"] == 5.0
    assert decision["risk_budget_usd"] == 50.0
    assert decision["exposure_pct"] == 50.0


def test_non_executable_signal_has_zero_position():
    decision = {
        "signal": 0,
        "risk_multiplier": 1.0,
        "levels": {"entry": None, "sl": None},
    }
    decision_pipeline.apply_risk_sizing(decision, capital=10_000, risk_pct=1.0)
    assert decision["position_oz"] == 0.0
    assert decision["exposure_pct"] == 0.0


def test_paper_journal_is_append_only_and_keeps_wait_decisions(tmp_path):
    report = SimpleNamespace(
        key="tech", score=0, confidence=50, verdict="محايد", flags={}
    )
    result = {
        "dec": {
            "decision_at": "2026-08-31T04:00:00+00:00",
            "signal": 0,
            "decision": "انتظار / محايد",
            "levels": {"entry": None},
            "research_only": True,
        },
        "reports": [report],
        "news": [],
        "last_price": 4500.0,
    }
    path = tmp_path / "journal.jsonl"
    first = paper_journal.append_record(result, path)
    second = paper_journal.append_record(result, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert first["signal"] == 0
    assert first["run_id"] != second["run_id"]


def test_demo_execution_window_is_limited_to_tested_utc_time():
    assert within_execution_window("2026-09-02T18:20:00+00:00") is True
    assert within_execution_window("2026-09-02T17:20:00+00:00") is False
    assert seconds_until_execution_window("2026-09-02T17:20:00+00:00") == 600
    assert seconds_until_execution_window("2026-09-02T18:00:00+00:00") == 0
    assert seconds_until_execution_window("2026-09-02T19:00:00+00:00") == 81_000


def test_demo_loop_retries_after_transient_service_error(monkeypatch, capsys):
    calls = iter([RuntimeError("temporary MT5 failure"), KeyboardInterrupt()])

    def fake_run_once(*, execute_demo, promotion_report_path=None):
        result = next(calls)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(mt5_demo_service, "run_once", fake_run_once)
    monkeypatch.setattr(mt5_demo_service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(sys, "argv", ["mt5_demo_service.py", "--loop"])

    try:
        mt5_demo_service.main()
    except KeyboardInterrupt:
        pass

    output = capsys.readouterr().out
    assert '"status": "service_error"' in output
    assert '"error_type": "RuntimeError"' in output
    assert '"retry_seconds": 300' in output


def test_demo_promotion_gate_fails_closed_for_missing_report(tmp_path):
    gate = mt5_demo_service.load_promotion_gate(tmp_path / "missing.json")
    assert gate["promotion_allowed"] is False
    assert gate["status"] == "missing_or_invalid"

from types import SimpleNamespace

import telegram_notifier


def _report(key, name, *, weight=0, flags=None):
    return SimpleNamespace(
        key=key, name=name, icon="X", verdict="محايد", score=0,
        summary="summary", weight=weight, flags=flags or {},
    )


def test_message_separates_votes_gates_and_experiments():
    decision = {
        "levels": {}, "decision": "انتظار", "final_score": 0,
        "confidence": 20, "agreement": 0, "research_only": True,
        "risk_multiplier": 1,
    }
    reports = [
        _report("tech", "technical"),
        _report("risk", "risk", weight=0.2),
        _report("numeric_surprise_experimental", "surprise",
                flags={"experimental": True, "non_voting": True}),
    ]
    text = telegram_notifier.build_signal_message(
        decision, 2000, reports, [], {"status": "ok", "actions": []}
    )
    assert "technical: محايد" in text
    assert "بوابات الأمان غير المصوّتة" in text
    assert "مراقبة تجريبية" in text
    assert "NFP Shadow" in text
    assert "المجلس منقسم" not in text
    assert "لم تجتز شروط الجودة" in text

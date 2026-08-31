import json

import groq_event_intelligence as gei


def test_no_key_means_no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(gei.env, "get", lambda *args: "")
    monkeypatch.setattr(gei.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    out = gei.analyze(["Gold rises"], cache_path=str(tmp_path / "c.json"))
    assert out["status"] == "unavailable"


def test_valid_response_is_cached(monkeypatch, tmp_path):
    result = {
        "event_type": "rates", "gold_impact": "bullish", "magnitude": 70,
        "horizon_hours": 24, "novelty": 60, "confidence": 80,
        "rationale": "real yields declined",
    }
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(result)}}]}
    calls = []
    monkeypatch.setattr(gei.requests, "post", lambda *a, **k: calls.append(1) or Response())
    cache = tmp_path / "cache.json"
    first = gei.analyze(["Headline A"], api_key="test", cache_path=str(cache))
    second = gei.analyze(["Headline A"], api_key="test", cache_path=str(cache))
    assert first["status"] == "ok" and first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 1

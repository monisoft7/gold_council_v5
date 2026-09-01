import json

import event_intelligence as ei
import llm_gateway


SETTING = llm_gateway.LLMSettings("B.AI", "secret", "https://example.test/v1", "free")


def test_network_is_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(ei.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    result = ei.analyze(["Gold rises"], selected=SETTING,
                        cache_path=str(tmp_path / "cache.json"))
    assert result["status"] == "cache_miss"


def test_markdown_json_is_validated_and_cached(monkeypatch, tmp_path):
    value = {"event_type": "rates", "gold_impact": "bullish", "magnitude": 70,
             "horizon_hours": 24, "novelty": 60, "confidence": 80,
             "rationale": "yields declined"}
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content":
                    "```json\n" + json.dumps(value) + "\n```"}}]}
    calls = []
    monkeypatch.setattr(ei.requests, "post", lambda *a, **k: calls.append(1) or Response())
    cache = tmp_path / "cache.json"
    first = ei.analyze(["Gold rises"], selected=SETTING, allow_network=True,
                       cache_path=str(cache))
    second = ei.analyze(["Gold rises"], selected=SETTING,
                        cache_path=str(cache))
    assert first["status"] == "ok" and second["cached"] is True
    assert len(calls) == 1


def test_empty_response_retries_then_fails_safely(monkeypatch, tmp_path):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": ""}}]}
    calls = []
    monkeypatch.setattr(ei.requests, "post", lambda *a, **k: calls.append(1) or Response())
    result = ei.analyze(["Gold rises"], selected=SETTING, allow_network=True,
                        cache_path=str(tmp_path / "cache.json"))
    assert result["status"] == "invalid"
    assert len(calls) == 2


def test_rate_limit_returns_safe_status(monkeypatch, tmp_path):
    class Response:
        status_code = 429
    monkeypatch.setattr(ei.requests, "post", lambda *a, **k: Response())
    result = ei.analyze(["Gold rises"], selected=SETTING, allow_network=True,
                        cache_path=str(tmp_path / "cache.json"))
    assert result["status"] == "rate_limited"
    assert "url" not in result


def test_json_generation_error_retries_without_json_mode(monkeypatch, tmp_path):
    value = {"event_type": "rates", "gold_impact": "neutral", "magnitude": 10,
             "horizon_hours": 24, "novelty": 10, "confidence": 70,
             "rationale": "already priced"}
    class Failed:
        status_code = 400
        def json(self):
            return {"error": {"message": "Failed to generate JSON"}}
    class Success:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": json.dumps(value)}}]}
    payloads = []
    def post(*args, **kwargs):
        payloads.append(kwargs["json"])
        return Failed() if len(payloads) == 1 else Success()
    monkeypatch.setattr(ei.requests, "post", post)
    result = ei.analyze(["Gold flat"], selected=SETTING, allow_network=True,
                        cache_path=str(tmp_path / "cache.json"))
    assert result["status"] == "ok"
    assert "response_format" in payloads[0]
    assert "response_format" not in payloads[1]

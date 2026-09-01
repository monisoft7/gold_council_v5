import llm_gateway
import council
from types import SimpleNamespace


def test_bai_is_preferred_when_configured(monkeypatch):
    values = {
        "BAI_API_KEY": "test-bai",
        "BAI_BASE_URL": "",
        "BAI_MODEL": "",
        "OPENAI_API_KEY": "test-openai",
    }
    monkeypatch.setattr(llm_gateway.env, "get", lambda key, default="": values.get(key, default))
    monkeypatch.setattr(llm_gateway, "_direct", lambda key: values.get(key, ""))
    selected = llm_gateway.settings()
    assert selected.provider == "B.AI"
    assert selected.base_url == "https://api.b.ai/v1"
    assert selected.model == "qwen3.8-flash"
    assert llm_gateway.available_settings()[0] == selected


def test_gateway_returns_none_without_keys(monkeypatch):
    monkeypatch.setattr(llm_gateway.env, "get", lambda key, default="": default)
    monkeypatch.setattr(llm_gateway, "_direct", lambda key: "")
    assert llm_gateway.settings() is None


def test_chairman_fails_over_to_next_provider(monkeypatch):
    first = llm_gateway.LLMSettings("B.AI", "x", "https://one", "m1")
    second = llm_gateway.LLMSettings("Groq", "y", "https://two", "m2")
    monkeypatch.setattr(llm_gateway, "available_settings", lambda: [first, second])

    class Completions:
        def __init__(self, fail):
            self.fail = fail
        def create(self, **kwargs):
            if self.fail:
                raise RuntimeError("provider unavailable")
            message = SimpleNamespace(content="memo")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    clients = {
        "B.AI": SimpleNamespace(chat=SimpleNamespace(completions=Completions(True))),
        "Groq": SimpleNamespace(chat=SimpleNamespace(completions=Completions(False))),
    }
    monkeypatch.setattr(
        llm_gateway, "client_and_settings",
        lambda selected=None: (clients[selected.provider], selected),
    )
    decision = {
        "final_score": 0, "decision": "انتظار", "confidence": 40,
        "levels": {}, "vetoed": None,
    }
    memo, status = council.llm_chairman([], decision, [], 3000)
    assert memo == "memo"
    assert "Groq" in status

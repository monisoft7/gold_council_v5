# -*- coding: utf-8 -*-
"""اختيار موحد وآمن لمزوّد LLM المتوافق مع OpenAI."""
from __future__ import annotations

from dataclasses import dataclass
import os

from env_loader import env


BAI_DEFAULT_BASE = "https://api.b.ai/v1"
GOROUTER_DEFAULT_BASE = "https://gorouter.app/v1"
KKTOKEN_DEFAULT_BASE = "https://kktoken.cc/v1"


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str | None
    model: str


def _direct(key):
    """يقرأ الاسم نفسه فقط حتى لا تحول aliases مفتاح Groq إلى OpenAI."""
    return env.kv.get(key) or os.environ.get(key, "")


def available_settings() -> list[LLMSettings]:
    """مزودون مستقلون بالترتيب: المجاني الموثق ثم الاحتياطيات."""
    available = []
    provider_specs = (
        ("B.AI", "BAI", BAI_DEFAULT_BASE, "qwen3.8-flash"),
        ("GoRouter", "GOROUTER", GOROUTER_DEFAULT_BASE, "claude-opus-5"),
        ("KKToken", "KKTOKEN", KKTOKEN_DEFAULT_BASE, "claude-opus-5"),
    )
    for provider, prefix, default_base, default_model in provider_specs:
        api_key = _direct(f"{prefix}_API_KEY")
        if not api_key:
            continue
        available.append(LLMSettings(
            provider=provider,
            api_key=api_key,
            base_url=env.get(f"{prefix}_BASE_URL") or default_base,
            model=env.get(f"{prefix}_MODEL") or default_model,
        ))
    openai_key = _direct("OPENAI_API_KEY") or _direct("OPENAI_KEY")
    if openai_key:
        available.append(LLMSettings(
            provider="OpenAI-compatible", api_key=openai_key,
            base_url=env.get("OPENAI_BASE_URL") or None,
            model=env.get("OPENAI_MODEL") or "gpt-4o-mini",
        ))
    groq_key = _direct("GROQ_API_KEY")
    if groq_key:
        available.append(LLMSettings(
            provider="Groq", api_key=groq_key,
            base_url="https://api.groq.com/openai/v1",
            model=env.get("GROQ_MODEL") or "llama-3.3-70b-versatile",
        ))
    return available


def settings() -> LLMSettings | None:
    available = available_settings()
    return available[0] if available else None


def client_and_settings(selected=None):
    selected = selected or settings()
    if selected is None:
        return None, None
    from openai import OpenAI
    return OpenAI(
        api_key=selected.api_key,
        base_url=selected.base_url,
        timeout=45.0,
        max_retries=1,
    ), selected

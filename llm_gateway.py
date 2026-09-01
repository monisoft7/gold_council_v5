# -*- coding: utf-8 -*-
"""اختيار موحد وآمن لمزوّد LLM المتوافق مع OpenAI."""
from __future__ import annotations

from dataclasses import dataclass
import os

from env_loader import env


CONDUIT_DEFAULT_BASE = "https://conduit.ozdoev.net/v1"


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
    """قائمة failover: Conduit ثم OpenAI-compatible ثم Groq."""
    available = []
    conduit_key = env.get("CONDUIT_API_KEY")
    if conduit_key:
        available.append(LLMSettings(
            provider="Conduit", api_key=conduit_key,
            base_url=env.get("CONDUIT_BASE_URL") or CONDUIT_DEFAULT_BASE,
            model=env.get("CONDUIT_MODEL") or "gpt-5-mini",
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
    return OpenAI(api_key=selected.api_key, base_url=selected.base_url), selected

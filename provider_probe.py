# -*- coding: utf-8 -*-
"""فحص آمن لمزوّدي OpenAI-compatible دون طباعة المفاتيح."""
from __future__ import annotations

import argparse

import requests

from env_loader import env


PROVIDERS = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_BASE_URL",
               "https://generativelanguage.googleapis.com/v1beta/openai"),
    "groq": ("GROQ_API_KEY", "GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL",
                   "https://openrouter.ai/api/v1"),
    "bai": ("BAI_API_KEY", "BAI_BASE_URL", "https://api.b.ai/v1"),
    "gorouter": ("GOROUTER_API_KEY", "GOROUTER_BASE_URL", "https://gorouter.app/v1"),
    "kktoken": ("KKTOKEN_API_KEY", "KKTOKEN_BASE_URL", "https://kktoken.cc/v1"),
}


def _credentials(provider):
    key_name, base_name, default_base = PROVIDERS[provider]
    return env.get(key_name), (env.get(base_name) or default_base).rstrip("/")


def list_models(provider, timeout=30):
    key, base = _credentials(provider)
    if not key:
        raise RuntimeError(f"missing {PROVIDERS[provider][0]}")
    response = requests.get(
        f"{base}/models", headers={"Authorization": f"Bearer {key}"},
        timeout=timeout,
    )
    response.raise_for_status()
    return sorted(item["id"] for item in response.json().get("data", []) if item.get("id"))


def probe_chat(provider, model, timeout=30):
    key, base = _credentials(provider)
    if not key:
        raise RuntimeError(f"missing {PROVIDERS[provider][0]}")
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content":
                          "Return JSON only with one field: status=ok"}],
            "temperature": 0,
            "max_tokens": 80,
            "response_format": {"type": "json_object"},
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return payload["choices"][0]["message"].get("content", "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=PROVIDERS)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    if args.list:
        models = list_models(args.provider)
        print(f"{args.provider}: {len(models)} model(s)")
        print("\n".join(models))
        return
    if not args.model:
        parser.error("--model is required unless --list is used")
    print(probe_chat(args.provider, args.model))


if __name__ == "__main__":
    main()

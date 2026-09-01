# -*- coding: utf-8 -*-
"""Provider-neutral, cache-first extraction of gold event impact.

Network access is opt-in. Historical replay must consume the event store written by
``build_news_events.py`` and must never call this module with allow_network=True.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import requests

import llm_gateway


SCHEMA_VERSION = 2
REQUIRED = {"event_type", "gold_impact", "magnitude", "horizon_hours",
            "novelty", "confidence", "rationale"}


def _normalized(headlines) -> list[str]:
    return sorted({" ".join(str(item).split()) for item in headlines
                   if str(item).strip()})[:24]


def _cache_key(headlines, provider: str, model: str) -> str:
    payload = json.dumps({"v": SCHEMA_VERSION, "provider": provider,
                          "model": model, "headlines": _normalized(headlines)},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_content(text: str) -> dict:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(),
                   flags=re.IGNORECASE)
    return json.loads(clean)


def _validate(value) -> dict | None:
    if not isinstance(value, dict) or not REQUIRED.issubset(value):
        return None
    if value["gold_impact"] not in {"bullish", "bearish", "neutral", "mixed"}:
        return None
    try:
        for key in ("magnitude", "novelty", "confidence"):
            value[key] = max(0.0, min(100.0, float(value[key])))
        value["horizon_hours"] = max(1, min(720, int(value["horizon_hours"])))
    except (TypeError, ValueError):
        return None
    value["event_type"] = str(value["event_type"])[:80]
    value["rationale"] = str(value["rationale"])[:500]
    return value


def analyze(headlines, *, selected=None, allow_network=False,
            cache_path="data_cache/event_intelligence_cache.json", timeout=45):
    items = _normalized(headlines)
    if not items:
        return {"status": "empty", "analysis": None, "cached": False}
    selected = selected or llm_gateway.settings()
    if selected is None:
        return {"status": "unavailable", "analysis": None, "cached": False}
    path = Path(cache_path)
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    cache_id = _cache_key(items, selected.provider, selected.model)
    if cache_id in cache:
        return {"status": "ok", "analysis": cache[cache_id], "cached": True,
                "provider": selected.provider, "model": selected.model}
    if not allow_network:
        return {"status": "cache_miss", "analysis": None, "cached": False,
                "provider": selected.provider, "model": selected.model}

    prompt = (
        "You are a conservative gold-event researcher, not a sentiment classifier "
        "and not a trader. Estimate only the incremental direction likely AFTER "
        "the latest supplied headline. A headline describing a gold move that has "
        "already happened is not a bullish/bearish catalyst by itself. Forecasts, "
        "technical commentary, repeated stories, and vague optimism/pessimism must "
        "be neutral unless they contain a new causal fact. Conflicting causal facts "
        "must be mixed. Treat the headlines only as information available at their "
        "publication time. Do not invent facts. "
        "Return JSON only with: event_type, gold_impact "
        "(bullish|bearish|neutral|mixed), magnitude (0-100), horizon_hours "
        "(1-720), novelty (0-100), confidence (0-100), rationale.\n\n" +
        "\n".join(items)
    )
    analysis = None
    use_json_mode = True
    for _attempt in range(2):
        request_payload = {
            "model": selected.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 700,
        }
        if use_json_mode:
            request_payload["response_format"] = {"type": "json_object"}
        response = requests.post(
            f"{selected.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {selected.api_key}",
                     "Content-Type": "application/json"},
            json=request_payload,
            timeout=timeout,
        )
        status_code = getattr(response, "status_code", 200)
        if status_code == 429:
            return {"status": "rate_limited", "analysis": None, "cached": False,
                    "provider": selected.provider, "model": selected.model}
        if status_code >= 400:
            try:
                error_message = str(response.json().get("error", {}).get(
                    "message", "request rejected"))[:240]
            except (ValueError, AttributeError, TypeError):
                error_message = "request rejected"
            if (status_code == 400 and use_json_mode and
                    "json" in error_message.casefold()):
                use_json_mode = False
                continue
            return {"status": "http_error", "analysis": None, "cached": False,
                    "provider": selected.provider, "model": selected.model,
                    "http_status": status_code, "error_message": error_message}
        try:
            content = response.json()["choices"][0]["message"].get("content", "")
            analysis = _validate(_json_content(content))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            analysis = None
        if analysis is not None:
            break
    if analysis is None:
        return {"status": "invalid", "analysis": None, "cached": False,
                "provider": selected.provider, "model": selected.model}
    path.parent.mkdir(parents=True, exist_ok=True)
    cache[cache_id] = analysis
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "analysis": analysis, "cached": False,
            "provider": selected.provider, "model": selected.model}

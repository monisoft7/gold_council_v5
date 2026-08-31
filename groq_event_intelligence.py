# -*- coding: utf-8 -*-
"""استخراج حدث مالي من عناوين مجمعة عبر Groq مع كاش وفشل آمن.

هذه الطبقة لا تصدر BUY/SELL ولا تستبدل البيانات الرسمية. وظيفتها فقط تحويل
نصوص الأخبار إلى حقائق تفسيرية منظمة يمكن لوكيل الماكرو تدقيقها.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import requests

from env_loader import env


ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
SCHEMA_VERSION = 1


def _normalized(headlines):
    return sorted({" ".join(str(h).split()) for h in headlines if str(h).strip()})[:20]


def _cache_key(headlines, model):
    payload = json.dumps({"v": SCHEMA_VERSION, "model": model,
                          "headlines": _normalized(headlines)},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _validate(value):
    required = {"event_type", "gold_impact", "magnitude", "horizon_hours",
                "novelty", "confidence", "rationale"}
    if not isinstance(value, dict) or not required.issubset(value):
        return None
    if value["gold_impact"] not in ("bullish", "bearish", "neutral", "mixed"):
        return None
    for key in ("magnitude", "novelty", "confidence"):
        value[key] = max(0, min(100, float(value[key])))
    value["horizon_hours"] = max(1, min(720, int(value["horizon_hours"])))
    return value


def analyze(headlines, *, api_key=None, model=None,
            cache_path="data_cache/groq_event_cache.json", timeout=30):
    items = _normalized(headlines)
    if not items:
        return {"status": "empty", "analysis": None, "cached": False}
    key = api_key or env.get("GROQ_API_KEY")
    if not key:
        legacy_key = env.get("OPENAI_API_KEY")
        legacy_base = env.get("OPENAI_BASE_URL").lower()
        if legacy_key.startswith("gsk_") or "groq.com" in legacy_base:
            key = legacy_key
    if not key:
        return {"status": "unavailable", "analysis": None, "cached": False}
    model = model or env.get("GROQ_MODEL") or DEFAULT_MODEL
    path = Path(cache_path)
    cache = _load_cache(path)
    cache_id = _cache_key(items, model)
    if cache_id in cache:
        return {"status": "ok", "analysis": cache[cache_id], "cached": True}

    prompt = ("حلل العناوين التالية كحدث واحد مؤثر في الذهب. لا تخمّن أرقاماً "
              "غير مذكورة ولا تصدر توصية تداول. أعد JSON فقط بالمفاتيح: "
              "event_type, gold_impact (bullish|bearish|neutral|mixed), "
              "magnitude (0-100), horizon_hours, novelty (0-100), "
              "confidence (0-100), rationale.\n\n" + "\n".join(items))
    response = requests.post(ENDPOINT, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json",
    }, json={
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_completion_tokens": 350,
        "response_format": {"type": "json_object"},
    }, timeout=timeout)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    analysis = _validate(json.loads(content))
    if analysis is None:
        return {"status": "invalid", "analysis": None, "cached": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    cache[cache_id] = analysis
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "ok", "analysis": analysis, "cached": False}

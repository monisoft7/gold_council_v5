# -*- coding: utf-8 -*-
"""وكيل مفاجأة اقتصادية سببي وتجريبي.

المصدر الأسبوعي المستخدم هنا مصدر بحثي غير رسمي. وقت إتاحة ``actual`` هو
وقت الجلب الفعلي، لا وقت الإصدار المفترض، حتى لا يتسرب المستقبل إلى الاختبار.
الوكيل يبدأ بوزن صفر إلى أن تتكون عينة تاريخية مستقلة كافية.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

import pandas as pd
import requests

from agents import AgentReport


CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
SOURCE_NAME = "ForexFactory weekly JSON mirror (unofficial)"
USER_AGENT = {"User-Agent": "GoldCouncil/1.0 causal-research"}


class CalendarFetchError(RuntimeError):
    def __init__(self, message: str, *, status_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class EconomicValue:
    value: float
    unit: str


def parse_economic_value(raw: Any) -> EconomicValue | None:
    """Parse values such as ``-23K``, ``0.3%``, ``$1.2B`` and ``(4.1)``."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    text = str(raw).strip().replace(",", "").replace("−", "-")
    if not text or text.casefold() in {"none", "null", "n/a", "na", "-"}:
        return None
    negative_parentheses = text.startswith("(") and text.endswith(")")
    unit = "%" if "%" in text else "number"
    suffix_match = re.search(r"([KMBT])\s*%?$", text, flags=re.IGNORECASE)
    multiplier = 1.0
    if suffix_match:
        suffix = suffix_match.group(1).upper()
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[suffix]
        unit = suffix
    cleaned = re.sub(r"[^0-9.+-]", "", text)
    try:
        value = float(cleaned) * multiplier
    except (TypeError, ValueError):
        return None
    if negative_parentheses:
        value = -abs(value)
    return EconomicValue(value=value, unit=unit)


def _gold_polarity(title: str) -> int:
    """Gold sign for a positive actual-minus-consensus surprise.

    ``+1`` means a higher-than-forecast value is normally gold-positive;
    ``-1`` means it is normally gold-negative through USD/rates. Unknown
    releases return zero rather than inventing a direction.
    """
    text = title.casefold()
    positive = ("unemployment rate", "jobless claims", "unemployment claims")
    negative = (
        "consumer price", " cpi", "inflation", "pce price", "producer price",
        " ppi", "non-farm", "nonfarm", "payroll", "employment change",
        "average hourly earnings", "retail sales", "gross domestic product",
        " gdp", "ism manufacturing", "ism services", "fed funds rate",
    )
    padded = f" {text}"
    if any(term in padded for term in positive):
        return 1
    if any(term in padded for term in negative):
        return -1
    return 0


def calculate_surprise(actual_raw: Any, forecast_raw: Any, previous_raw: Any,
                       title: str) -> dict | None:
    actual = parse_economic_value(actual_raw)
    forecast = parse_economic_value(forecast_raw)
    previous = parse_economic_value(previous_raw)
    if actual is None or forecast is None or actual.unit != forecast.unit:
        return None
    raw = actual.value - forecast.value
    # المقياس ليس z-score تاريخياً. إنه تطبيع مقاوم فقط لجعل الأحداث قابلة
    # للعرض معاً، ويظل تجريبياً حتى يتوفر تاريخ consensus كافٍ.
    reference_move = abs(forecast.value - previous.value) \
        if previous is not None and previous.unit == forecast.unit else 0.0
    floor = 0.1 if forecast.unit == "%" else max(abs(forecast.value) * 0.05, 1.0)
    scale = max(reference_move, floor)
    normalized = max(-4.0, min(4.0, raw / scale))
    polarity = _gold_polarity(title)
    gold_score = 100.0 * math.tanh(normalized) * polarity if polarity else 0.0
    return {
        "actual_value": actual.value,
        "forecast_value": forecast.value,
        "previous_value": previous.value if previous is not None else None,
        "unit": actual.unit,
        "surprise": raw,
        "normalized_surprise": normalized,
        "gold_polarity": polarity,
        "gold_score": round(gold_score, 2),
    }


def fetch_weekly_calendar(*, fetched_at=None, timeout: int = 20,
                          session=requests) -> pd.DataFrame:
    """Fetch the current week and timestamp what was knowable at collection."""
    try:
        response = session.get(CALENDAR_URL, headers=USER_AGENT, timeout=timeout)
    except requests.RequestException as exc:
        raise CalendarFetchError(f"calendar network error: {exc}") from None
    status = int(getattr(response, "status_code", 200))
    headers = getattr(response, "headers", {}) or {}
    retry_after_raw = headers.get("Retry-After")
    try:
        retry_after = int(retry_after_raw) if retry_after_raw else None
    except (TypeError, ValueError):
        retry_after = None
    if status == 429:
        raise CalendarFetchError(
            "calendar rate limited (HTTP 429)", status_code=429,
            retry_after=retry_after,
        )
    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CalendarFetchError(
            f"calendar HTTP error {status}", status_code=status,
            retry_after=retry_after,
        ) from None
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("economic calendar payload is not a list")
    observed = pd.Timestamp(fetched_at or pd.Timestamp.now(tz="UTC"))
    observed = observed.tz_localize("UTC") if observed.tzinfo is None \
        else observed.tz_convert("UTC")
    rows = []
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        release = pd.to_datetime(raw.get("date"), errors="coerce", utc=True)
        if pd.isna(release):
            continue
        country = str(raw.get("country") or "").upper().strip()
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        actual = raw.get("actual")
        forecast = raw.get("forecast")
        previous = raw.get("previous")
        calc = calculate_surprise(actual, forecast, previous, title)
        rows.append({
            "source": SOURCE_NAME,
            "country": country,
            "title": title,
            "impact": str(raw.get("impact") or "").strip(),
            "release_time": release,
            "forecast": forecast,
            "previous": previous,
            "actual": actual,
            "fetched_at": observed,
            "forecast_available_at": observed if parse_economic_value(forecast) else pd.NaT,
            "actual_available_at": observed if parse_economic_value(actual) else pd.NaT,
            **(calc or {}),
        })
    return pd.DataFrame(rows).sort_values(["release_time", "title"]).reset_index(drop=True)


def merge_snapshots(existing: pd.DataFrame | None, current: pd.DataFrame) -> pd.DataFrame:
    """Append observations without rewriting what an earlier fetch knew."""
    frames = [frame for frame in (existing, current) if frame is not None and not frame.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    for column in ("release_time", "fetched_at", "forecast_available_at",
                   "actual_available_at"):
        if column in out:
            out[column] = pd.to_datetime(out[column], errors="coerce", utc=True)
    return (out.drop_duplicates(subset=["source", "country", "title", "release_time",
                                        "fetched_at"], keep="last")
            .sort_values(["fetched_at", "release_time", "title"])
            .reset_index(drop=True))


def economic_surprise_agent(history: pd.DataFrame | None, *, as_of=None,
                            max_age_hours: float = 12.0) -> AgentReport:
    """Use only actual values whose collection timestamp is at/before ``as_of``."""
    if history is None or history.empty:
        return AgentReport(
            key="numeric_surprise_experimental", name="وكيل المفاجأة الرقمية",
            icon="🔢", role="Actual مقابل Consensus (بحثي، لا يصوّت)",
            score=0, confidence=0, verdict="لا بيانات", weight=0.0,
            summary="لم يبدأ أرشيف المفاجآت بعد", bullets=[],
            flags={"experimental": True, "non_voting": True},
        )
    now = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    frame = history.copy()
    frame["actual_available_at"] = pd.to_datetime(
        frame.get("actual_available_at"), errors="coerce", utc=True
    )
    frame["release_time"] = pd.to_datetime(frame.get("release_time"), errors="coerce", utc=True)
    frame = frame[
        frame["actual_available_at"].notna()
        & (frame["actual_available_at"] <= now)
        & (frame["actual_available_at"] >= now - pd.Timedelta(hours=max_age_hours))
        & frame.get("gold_score", pd.Series(index=frame.index, dtype=float)).notna()
    ].copy()
    if frame.empty:
        return AgentReport(
            key="numeric_surprise_experimental", name="وكيل المفاجأة الرقمية",
            icon="🔢", role="Actual مقابل Consensus (بحثي، لا يصوّت)",
            score=0, confidence=20, verdict="لا إصدار حديث", weight=0.0,
            summary="لا توجد مفاجأة رقمية مكتملة ومتاحة زمنياً", bullets=[],
            flags={"experimental": True, "non_voting": True},
        )
    # أحدث لقطة فقط لكل إصدار، كي لا يضاعف polling وزن الحدث.
    frame = (frame.sort_values("fetched_at")
             .drop_duplicates(["country", "title", "release_time"], keep="last"))
    known = frame[pd.to_numeric(frame["gold_polarity"], errors="coerce") != 0]
    if known.empty:
        score = 0.0
    else:
        score = float(pd.to_numeric(known["gold_score"], errors="coerce").mean())
    confidence = min(65.0, 35.0 + len(known) * 7.5) if len(known) else 20.0
    bullets = [
        f"{row.title}: actual={row.actual} مقابل forecast={row.forecast}"
        for row in frame.itertuples()
    ][:5]
    verdict = "شراء تجريبي" if score >= 15 else "بيع تجريبي" if score <= -15 else "محايد"
    return AgentReport(
        key="numeric_surprise_experimental", name="وكيل المفاجأة الرقمية",
        icon="🔢", role="Actual مقابل Consensus (بحثي، لا يصوّت)",
        score=round(score, 2), confidence=confidence, verdict=verdict, weight=0.0,
        summary=f"{len(frame)} إصدار متاح؛ الإشارة غير معتمدة للتداول",
        bullets=bullets,
        flags={"experimental": True, "non_voting": True,
               "observations": len(frame), "known_polarity": len(known)},
    )

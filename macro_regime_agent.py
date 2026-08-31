# -*- coding: utf-8 -*-
"""وكيل ماكرو رقمي مبني على البيانات الرسمية point-in-time."""
from __future__ import annotations

import pandas as pd

from agents import AgentReport


def _verdict(score):
    if score >= 25: return "شراء 🟢"
    if score <= -25: return "بيع 🔴"
    return "محايد ⚪"


def macro_regime_agent(history: pd.DataFrame, as_of=None) -> AgentReport:
    if history is None or history.empty or as_of is None:
        return AgentReport(
            key="macro_data", name="وكيل الماكرو الرسمي", icon="🏛️",
            role="يقرأ العوائد الحقيقية والدولار والإصدارات الرسمية",
            score=0, confidence=20, verdict="بيانات غير كافية",
            summary="لا توجد لقطة ماكرو point-in-time", bullets=[])
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    frame = history.copy()
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    frame = frame.loc[frame["available_at"] <= cutoff].tail(30)
    if len(frame) < 10:
        return AgentReport(
            key="macro_data", name="وكيل الماكرو الرسمي", icon="🏛️",
            role="يقرأ العوائد الحقيقية والدولار والإصدارات الرسمية",
            score=0, confidence=25, verdict="بيانات غير كافية",
            summary=f"تتوفر {len(frame)} لقطات فقط", bullets=[])

    score, bullets, used = 0.0, [], 0
    specs = [
        ("real_yield_10y_value", -1, 24, "العائد الحقيقي 10Y"),
        ("broad_dollar_value", -1, 22, "الدولار الواسع"),
        ("vix_value", +1, 10, "VIX"),
    ]
    for col, gold_sign, weight, label in specs:
        values = pd.to_numeric(frame.get(col), errors="coerce").dropna()
        if len(values) < 10:
            continue
        if "yield" in col:
            change = float(values.iloc[-1] - values.iloc[-10])
            scale = 0.15
            display = f"{change:+.2f} نقطة"
        else:
            change = float(values.iloc[-1] / values.iloc[-10] - 1)
            scale = 0.015
            display = f"{change:+.2%}"
        direction = 1 if change * gold_sign > 0 else (-1 if change * gold_sign < 0 else 0)
        strength = min(1.0, abs(change) / scale) if scale else 0
        contribution = direction * weight * strength
        score += contribution; used += 1
        bullets.append(f"{label}: تغير 10 جلسات {display} → أثر ذهب {contribution:+.1f}")

    # اتجاه التضخم/الفائدة بطيء؛ نعرضه كسياق ولا نحوله إلى شراء آلي.
    for col, label in (("cpi_value", "CPI"), ("fed_funds_value", "Fed Funds")):
        if col not in frame:
            continue
        values = pd.to_numeric(frame[col], errors="coerce").dropna()
        if len(values):
            bullets.append(f"{label}: آخر قيمة أولية متاحة {values.iloc[-1]:.2f}")
    score = max(-100, min(100, score))
    confidence = min(85, 35 + used * 12 + abs(score) * 0.25)
    return AgentReport(
        key="macro_data", name="وكيل الماكرو الرسمي", icon="🏛️",
        role="يقرأ العوائد الحقيقية والدولار والإصدارات الرسمية point-in-time",
        score=round(score, 1), confidence=round(confidence, 0),
        verdict=_verdict(score),
        summary=f"نظام ماكرو من {used} محركات رسمية؛ المحصلة {score:+.1f}",
        bullets=bullets, weight=0.25)

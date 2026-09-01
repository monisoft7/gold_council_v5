# -*- coding: utf-8 -*-
"""Experimental point-in-time news-impact agent (non-voting until validated)."""
from __future__ import annotations

import pandas as pd

from agents import AgentReport, _verdict


def news_impact_agent(history: pd.DataFrame | None, *, as_of) -> AgentReport:
    report = AgentReport(
        key="news_impact_experimental", name="وكيل أثر الأخبار التجريبي",
        icon="🧪", role="تحويل الأخبار التاريخية إلى أثر سببي على الذهب",
        weight=0.0, flags={"experimental": True, "voting_enabled": False},
    )
    if history is None or history.empty:
        report.summary = "لا يوجد مخزن أحداث تاريخي متاح حتى زمن القرار."
        return report
    frame = history.copy()
    frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True,
                                             errors="coerce")
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    eligible = frame.dropna(subset=["available_at"])
    eligible = eligible[eligible["available_at"] <= cutoff].sort_values("available_at")
    if eligible.empty:
        report.summary = "لا توجد نتيجة منشورة قبل زمن القرار؛ لم تُستخدم بيانات مستقبلية."
        return report
    latest = eligible.iloc[-1]
    age_hours = (cutoff - latest["available_at"]).total_seconds() / 3600
    horizon = max(1.0, float(latest.get("horizon_hours", 24)))
    if age_hours > horizon:
        report.summary = "آخر حدث تجاوز أفق تأثيره قبل زمن القرار."
        return report
    direction = {"bullish": 1, "bearish": -1}.get(str(latest.get("gold_impact")), 0)
    magnitude = float(latest.get("magnitude", 0))
    confidence = float(latest.get("confidence", 0))
    decay = max(0.0, 1.0 - age_hours / horizon)
    report.score = round(direction * magnitude * confidence / 100 * decay, 2)
    report.confidence = confidence
    report.verdict = _verdict(report.score)
    report.summary = str(latest.get("rationale", ""))
    report.bullets = [f"متاح منذ: {latest['available_at'].isoformat()}",
                      f"العمر: {age_hours:.1f} ساعة / الأفق: {horizon:.0f} ساعة",
                      "تجريبي: لا يشارك في تصويت المجلس"]
    return report

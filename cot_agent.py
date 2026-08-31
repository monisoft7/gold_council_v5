# -*- coding: utf-8 -*-
"""وكيل تمركزات CFTC للذهب؛ يستخدم بيانات كانت منشورة فعلاً فقط."""
from __future__ import annotations

import pandas as pd

from agents import AgentReport


def cot_positioning_agent(history: pd.DataFrame, as_of=None) -> AgentReport:
    required = {"cot_available_at", "cot_noncommercial_net", "cot_open_interest"}
    if history is None or history.empty or as_of is None or not required.issubset(history):
        return AgentReport(
            key="cot", name="وكيل تمركزات CFTC", icon="🏦",
            role="يراقب تمركزات المضاربين والمؤسسات في عقود ذهب COMEX",
            score=0, confidence=20, verdict="بيانات غير كافية",
            summary="أرشيف COT غير متاح", bullets=[])
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    frame = history.copy()
    frame["cot_available_at"] = pd.to_datetime(frame["cot_available_at"], utc=True)
    weekly = (frame.loc[frame["cot_available_at"] <= cutoff]
              .dropna(subset=["cot_available_at", "cot_noncommercial_net"])
              .drop_duplicates(subset=["cot_available_at"], keep="last")
              .sort_values("cot_available_at").tail(52))
    if len(weekly) < 8:
        return AgentReport(
            key="cot", name="وكيل تمركزات CFTC", icon="🏦",
            role="يراقب تمركزات المضاربين والمؤسسات في عقود ذهب COMEX",
            score=0, confidence=25, verdict="بيانات غير كافية",
            summary=f"تتوفر {len(weekly)} تقارير فقط", bullets=[])
    net = pd.to_numeric(weekly["cot_noncommercial_net"], errors="coerce")
    oi = pd.to_numeric(weekly["cot_open_interest"], errors="coerce")
    ratio = (net / oi.replace(0, pd.NA)).dropna()
    delta = float(net.iloc[-1] - net.iloc[-2])
    delta_ratio = float(delta / oi.iloc[-1]) if oi.iloc[-1] else 0.0
    percentile = float((ratio <= ratio.iloc[-1]).mean() * 100) if len(ratio) else 50.0
    trend_score = max(-24, min(24, delta_ratio / 0.03 * 18))
    extreme_score = 5 if percentile >= 80 else (-5 if percentile <= 20 else 0)
    score = trend_score + extreme_score
    crowded = percentile >= 95 or percentile <= 5
    verdict = "شراء 🟢" if score >= 15 else ("بيع 🔴" if score <= -15 else "محايد ⚪")
    bullets = [
        f"صافي غير التجاريين: {net.iloc[-1]:,.0f} عقد",
        f"التغير الأسبوعي: {delta:+,.0f} ({delta_ratio:+.2%} من الفائدة المفتوحة)",
        f"المئين خلال {len(ratio)} تقريراً: {percentile:.0f}%",
    ]
    if crowded:
        bullets.append("⚠️ تمركز مزدحم تاريخياً؛ يخفض الثقة ولا يعني انعكاساً آلياً")
    confidence = min(82, 45 + len(ratio) * 0.4 + abs(score) * 0.4 - (12 if crowded else 0))
    return AgentReport(
        key="cot", name="وكيل تمركزات CFTC", icon="🏦",
        role="يراقب تمركزات المضاربين والمؤسسات في عقود ذهب COMEX",
        score=round(score, 1), confidence=round(confidence, 0), verdict=verdict,
        summary=f"زخم تمركزات COT {score:+.1f}، مئين {percentile:.0f}%",
        bullets=bullets, weight=0.12,
        flags={"crowded_positioning": crowded})

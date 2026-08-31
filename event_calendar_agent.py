# -*- coding: utf-8 -*-
"""بوابة أحداث تاريخية؛ الخطر لا يتحول إلى صوت بيع."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

from agents import AgentReport


@lru_cache(maxsize=4)
def _load(path: str) -> pd.DataFrame:
    file = Path(path)
    if not file.exists():
        return pd.DataFrame(columns=["time", "title", "source", "section"])
    frame = pd.read_csv(file)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    return frame.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)


def _kind(row) -> str:
    text = f"{row.get('title', '')} {row.get('section', '')}".lower()
    if "fomc" in text or "federal reserve" in text: return "FOMC"
    if "nonfarm" in text or "nfp" in text or "payroll" in text: return "NFP"
    if "cpi" in text or "consumer price" in text: return "CPI"
    return "HIGH_IMPACT"


def event_calendar_agent(ref: datetime = None, events: pd.DataFrame = None,
                         events_path: str = "data_cache/events_2008_2026.csv") -> AgentReport:
    ref = pd.Timestamp(ref or datetime.now(timezone.utc))
    ref = ref.tz_localize("UTC") if ref.tzinfo is None else ref.tz_convert("UTC")
    frame = events.copy() if events is not None else _load(str(Path(events_path).resolve()))
    if frame.empty:
        return AgentReport(
            key="event", name="وكيل تقويم الأحداث", icon="📆",
            role="بوابة توقيت FOMC/CPI/NFP التاريخية",
            score=0, confidence=20, verdict="التقويم غير متاح",
            summary="لا يوجد تقويم أحداث قابل للقراءة", bullets=[], weight=0.0,
            flags={"trade_block": False, "risk_multiplier": 0.5,
                   "calendar_available": False})
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["time"]).copy()
    frame["event_kind"] = frame.apply(_kind, axis=1)
    coverage_start = frame["time"].min()
    coverage_end = frame["time"].max()
    # غياب حدث قريب لا يعني أن النافذة آمنة إذا كان تاريخ القرار خارج
    # نطاق الأرشيف نفسه. هذا يمنع تحويل نقص البيانات إلى إشارة أمان زائفة.
    if ref < coverage_start - pd.Timedelta(days=7) or ref > coverage_end + pd.Timedelta(days=7):
        return AgentReport(
            key="event", name="وكيل تقويم الأحداث", icon="📆",
            role="بوابة توقيت FOMC/CPI/NFP التاريخية",
            score=0, confidence=20, verdict="خارج تغطية التقويم",
            summary=(f"المرجع خارج التغطية {coverage_start.date()} — "
                     f"{coverage_end.date()}؛ خفض المخاطرة احترازياً"),
            bullets=["⚠️ لا يجوز اعتبار غياب البيانات نافذة آمنة"], weight=0.0,
            flags={"trade_block": False, "risk_multiplier": 0.5,
                   "calendar_available": False})

    # اكتمال التقويم يُقاس لكل عائلة على حدة، لا بأبعد حدث في الملف كله.
    # وجود FOMC مستقبلي مثلاً لا يثبت أن جداول CPI وNFP ما زالت مغطاة.
    required_kinds = ("FOMC", "CPI", "NFP")
    incomplete_kinds = []
    for kind in required_kinds:
        kind_times = frame.loc[frame["event_kind"] == kind, "time"]
        # موعد مستقبلي قريب يثبت وجود جدول منشور، أما فجوة تمتد أشهراً أو
        # سنوات قبل أول سجل فلا يجوز اعتبارها تغطية تاريخية.
        starts_too_late = (
            not kind_times.empty
            and ref < kind_times.min() - pd.Timedelta(days=45)
        )
        if kind_times.empty or starts_too_late \
                or ref > kind_times.max() + pd.Timedelta(days=7):
            incomplete_kinds.append(kind)

    nearby = frame.loc[(frame["time"] >= ref - pd.Timedelta(hours=6)) &
                       (frame["time"] <= ref + pd.Timedelta(days=7))].copy()
    bullets, block = [], False
    risk_multiplier = 0.5 if incomplete_kinds else 1.0
    if incomplete_kinds:
        bullets.append(
            "⚠️ تغطية غير مكتملة لعائلات: " + ", ".join(incomplete_kinds)
            + " — خفض الحجم احترازياً"
        )
    for _, row in nearby.head(5).iterrows():
        hours = (row["time"] - ref).total_seconds() / 3600
        kind = _kind(row)
        if -4 <= hours <= 24:
            block = True
            risk_multiplier = 0.0
            bullets.append(f"🔴 {kind} خلال {hours:+.1f} ساعة — منع دخول جديد")
        elif 24 < hours <= 72:
            risk_multiplier = min(risk_multiplier, 0.5)
            bullets.append(f"🟡 {kind} خلال {hours/24:.1f} يوم — خفض الحجم 50%")
        else:
            bullets.append(f"📌 {kind} خلال {hours/24:.1f} يوم")
    if not nearby.empty:
        nearby_count = len(nearby)
    else:
        nearby_count = 0
    if not bullets:
        bullets.append("✅ لا حدث عالي التأثير خلال 7 أيام")
    elif incomplete_kinds and nearby_count == 0:
        bullets.append("لا يمكن اعتبار غياب الحدث نافذة آمنة مع نقص التغطية")
    calendar_available = not incomplete_kinds
    if block:
        verdict = "منع تداول"
    elif risk_multiplier < 1 and incomplete_kinds:
        verdict = "تغطية جزئية"
    elif risk_multiplier < 1:
        verdict = "خفض مخاطرة"
    else:
        verdict = "نافذة آمنة"
    return AgentReport(
        key="event", name="وكيل تقويم الأحداث", icon="📆",
        role="بوابة توقيت تاريخية لـFOMC/CPI/NFP؛ لا تصوّت في الاتجاه",
        score=0, confidence=90 if nearby_count else (45 if incomplete_kinds else 70),
        verdict=verdict,
        summary=f"{nearby_count} أحداث قريبة؛ معامل المخاطرة {risk_multiplier:.1f}",
        bullets=bullets, weight=0.0,
        flags={"trade_block": block, "risk_multiplier": risk_multiplier,
               "calendar_available": calendar_available,
               "incomplete_kinds": incomplete_kinds})

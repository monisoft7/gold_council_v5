# -*- coding: utf-8 -*-
"""
وكيل أنماط الشموع اليابانية (Candlestick Pattern Recognition).
يكتشف أحدث 3 أنماط سعرية في الشموع الأخيرة ويقيّم أهميتها:

  • engulfing (بلع صاعد/هابط) — أقوى إشارة انعكاس.
  • hammer / shooting-star — إشارات قاع/قمة.
  • doji / spinning-top — تردد في السوق.
  • marubozu — قوة الاتجاه.
  • piercing-line / dark-cloud-cover — أنماط انعكاس كلاسيكية.

لا يستخدم look-ahead — يحسب على آخر 5 شموع فقط.
"""
import numpy as np
import pandas as pd

from agents import AgentReport


def _body(o, c):   return abs(c - o)
def _range(h, l):  return h - l
def _upper_wick(o, c, h): return h - max(o, c)
def _lower_wick(o, c, l): return min(o, c) - l


def detect_patterns(df: pd.DataFrame) -> list:
    """يكشف الأنماط على آخر 5 شموع ويرجع قائمة (نمط، اتجاه، إشارة، نقاط)."""
    out = []
    if len(df) < 3:
        return out
    recent = df.tail(5).reset_index(drop=True)
    for i in range(1, len(recent)):
        prev = recent.iloc[i - 1]; cur = recent.iloc[i]
        o, h, l, c = cur["open"], cur["high"], cur["low"], cur["close"]
        po, pc = prev["open"], prev["close"]

        body = _body(o, c); rng = max(_range(h, l), 0.0001)
        if body / rng < 0.10:
            out.append(("Doji (تردد)", "⚪", 0,
                        f"شمعة #{i+1} Doji — السوق متردد، تأكيد مطلوب من وكيل آخر"))
            continue

        # Bullish Engulfing
        if pc < po and c > o and c > po and o < pc and body > _body(po, pc):
            out.append(("Bullish Engulfing", "🟢", 22,
                        f"🟢 شمعة بلع صاعدة #{i+1} — إشارة انعكاس قوية للشراء"))
        # Bearish Engulfing
        if pc > po and c < o and c < po and o > pc and body > _body(po, pc):
            out.append(("Bearish Engulfing", "🔴", -22,
                        f"🔴 شمعة بلع هابطة #{i+1} — إشارة انعكاس قوية للبيع"))

        # Hammer
        up = _upper_wick(o, c, h); lo = _lower_wick(o, c, l)
        if lo >= 2 * body and up < body * 0.5 and c > o:
            out.append(("Hammer (قاع)", "🟢", 14,
                        f"🔨 Hammer في شمعة #{i+1} — قاع محتمل وذيل سفلي طويل"))
        # Shooting Star
        if up >= 2 * body and lo < body * 0.5 and c < o:
            out.append(("Shooting Star (قمة)", "🔴", -14,
                        f"🌠 Shooting star #{i+1} — قمة محتملة"))

        # Marubozu
        if up / rng < 0.05 and lo / rng < 0.05:
            direction = "صاعد" if c > o else "هابط"
            pts = 10 if direction == "صاعد" else -10
            out.append((f"Marubozu {direction}", "🟢" if pts > 0 else "🔴", pts,
                        f"🪵 شمعة #{i+1} بدون ظلال — إجماع {direction}"))

        # Piercing Line
        if pc < po and c > o and c > (po + pc) / 2 and o < pc:
            out.append(("Piercing Line", "🟢", 12,
                        f"🌅 اختراق صاعد #{i+1}"))
        # Dark Cloud Cover
        if pc > po and c < o and c < (po + pc) / 2 and o > pc:
            out.append(("Dark Cloud Cover", "🔴", -12,
                        f"☁️ غطاء داكن هابط #{i+1}"))
    return out


def pattern_agent(df: pd.DataFrame) -> AgentReport:
    if df is None or len(df) < 5:
        return AgentReport(
            key="pattern", name="وكيل أنماط الشموع", icon="🕯️",
            role="يكتشف أنماط الشموع اليابانية على آخر 5 جلسات",
            score=0, confidence=20, verdict="بيانات غير كافية",
            summary="بيانات شموع غير كافية", bullets=[])
    patterns = detect_patterns(df)
    if not patterns:
        return AgentReport(
            key="pattern", name="وكيل أنماط الشموع", icon="🕯️",
            role="يكتشف أنماط الشموع اليابانية على آخر 5 جلسات",
            score=0, confidence=40, verdict="⚪ لا أنماط لافتة",
            summary="لم يُكتشف نمط لافت في آخر 5 شموع",
            bullets=["لا توجد إشارات انعكاس أو استمرار قوية اليوم — يعتمد المجلس على باقي الوكلاء"])
    score = sum(p[2] for p in patterns)
    score = max(-100, min(100, score))
    conf = min(85, 50 + abs(score) * 0.4)
    return AgentReport(
        key="pattern", name="وكيل أنماط الشموع", icon="🕯️",
        role="يكتشف Bullish/Bearish Engulfing و Hammer و Marubozu و Doji",
        score=round(score, 1), confidence=round(conf, 0),
        verdict=("شراء قوي 🟢" if score >= 35 else
                 "شراء 🟢"      if score >= 15 else
                 "محايد ⚪"     if score > -15 else
                 "بيع 🔴"       if score > -35 else "بيع قوي 🔴"),
        summary=f"تم رصد {len(patterns)} نمط في آخر 5 شموع (محصلة {score:+.0f})",
        bullets=[p[3] for p in patterns[-6:]],  # أحدث 6 فقط
        weight=0.10)

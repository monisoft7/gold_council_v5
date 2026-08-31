# -*- coding: utf-8 -*-
"""محرك المخاطر V6 — الفجوة 2 من التشخيص التنفيذي.

- position_size: تحديد الحجم بالمخاطرة بالدولار (Volatility-adjusted عبر SL)
- kelly_fraction: ربع كيلي الآمن مع سقف
- dynamic_levels: SL/TP بمضاعفات ATR حسب الاتجاه
- CircuitBreaker: قاطع أمان يوقف التداول عند تجاوز الهبوط من القمة
- correlation_guard: حارس ارتباط الذهب/الدولار (كشف تغيّر النظام السعري)
"""
from dataclasses import dataclass


def position_size(entry: float, sl: float, capital: float, risk_pct: float = 1.0) -> float:
    """حجم الصفقة بوحدات الأونصة: risk$ / |entry - sl|.

    مثال: entry=2700, sl=2680, capital=10000, risk=1% → 100$/20$ = 5 أونصات.
    """
    if not entry or not sl or entry <= 0 or sl <= 0 or capital <= 0:
        return 0.0
    per_unit_risk = abs(entry - sl)
    if per_unit_risk <= 0:
        return 0.0
    risk_dollars = capital * risk_pct / 100.0
    return round(risk_dollars / per_unit_risk, 4)


def kelly_fraction(win_rate_pct: float, rr_ratio: float, cap: float = 0.25) -> float:
    """ربع معيار كيلي: f* = (p*b - q)/b ثم /4، مع سقف cap.

    win_rate_pct: نسبة الفوز التاريخية (0-100). rr_ratio: متوسط الرابح/متوسط الخاسر.
    """
    if rr_ratio <= 0 or win_rate_pct <= 0:
        return 0.0
    p = min(0.99, win_rate_pct / 100.0)
    q = 1.0 - p
    f = (p * rr_ratio - q) / rr_ratio
    return round(max(0.0, min(cap, f / 4.0)), 4)


def dynamic_levels(entry: float, atr: float, direction: int,
                   sl_mult: float = 1.5, tp1_mult: float = 2.0, tp2_mult: float = 3.0) -> dict:
    """مستويات ديناميكية بمضاعفات ATR. direction: 1 شراء / -1 بيع."""
    if direction not in (1, -1) or not atr or atr <= 0 or not entry or entry <= 0:
        return {"entry": entry, "sl": None, "tp1": None, "tp2": None, "rr": None}
    sl = entry - direction * sl_mult * atr
    tp1 = entry + direction * tp1_mult * atr
    tp2 = entry + direction * tp2_mult * atr
    rr = abs(tp1 - entry) / abs(entry - sl)
    return {"entry": round(entry, 2), "sl": round(sl, 2),
            "tp1": round(tp1, 2), "tp2": round(tp2, 2), "rr": round(rr, 2)}


class CircuitBreaker:
    """قاطع الأمان: يوقف التداول إذا هبطت المحفظة max_dd_pct% من قمتها."""

    def __init__(self, max_dd_pct: float = 5.0):
        self.max_dd_pct = max_dd_pct
        self.peak = None
        self.halted = False

    def update(self, equity: float) -> dict:
        if self.peak is None or equity > self.peak:
            self.peak = equity
        dd = (self.peak - equity) / self.peak * 100.0 if self.peak else 0.0
        self.halted = dd >= self.max_dd_pct
        return {"equity": round(equity, 2), "peak": round(self.peak, 2),
                "dd_pct": round(dd, 2), "halted": self.halted}

    def reset(self):
        self.peak = None
        self.halted = False


def correlation_guard(gold_returns, dxy_returns, anomaly_thresh: float = 0.3) -> dict:
    """حارس الارتباط: الذهب والدولار سالبا الارتباط عادةً.

    إذا أصبح الارتباط المتدحرج موجباً بقوة (> anomaly_thresh) → نظام سعري شاذ
    (رفع فائدة + أزمة معاً مثلاً) → نحذّر بدلاً من المنع لأن الإشارة قد تكون صالحة.
    يقبل pd.Series أو قوائم أرقام بنفس الطول.
    """
    import pandas as pd
    g = pd.Series(list(gold_returns), dtype="float64")
    d = pd.Series(list(dxy_returns), dtype="float64")
    if len(g) < 5 or len(d) < 5:
        return {"corr": None, "anomaly": False, "note": "بيانات غير كافية"}
    corr = float(g.corr(d))
    anomaly = corr > anomaly_thresh
    note = ("⚠ ارتباط موجب شاذ — النظام السعري تغيّر، خفّض حجم الصفقة"
            if anomaly else "ارتباط طبيعي (سالب/ضعيف)")
    return {"corr": round(corr, 3), "anomaly": anomaly, "note": note}

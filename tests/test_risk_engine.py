# -*- coding: utf-8 -*-
"""اختبارات محرك المخاطر — قيم متوقعة بدقة."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from risk_engine import (position_size, kelly_fraction, dynamic_levels,
                         CircuitBreaker, correlation_guard)


def test_position_size_exact():
    # مخاطرة 1% من 10000 = 100$ / مسافة وقف 20$ = 5 أونصات
    assert position_size(2700, 2680, 10000, 1.0) == 5.0
    # مدخلات فاسدة → صفر
    assert position_size(0, 2680, 10000, 1.0) == 0.0
    assert position_size(2700, 2700, 10000, 1.0) == 0.0


def test_kelly_quarter_with_cap():
    # p=0.6, b=1.5 → f*=(0.9-0.4)/1.5=0.333 → ربع كيلي=0.0833
    f = kelly_fraction(60.0, 1.5)
    assert 0.08 <= f <= 0.09
    # استراتيجية خاسرة → صفر
    assert kelly_fraction(30.0, 1.0) == 0.0
    # سقف
    assert kelly_fraction(95.0, 5.0) <= 0.25


def test_dynamic_levels_direction():
    lv = dynamic_levels(2700, 10, direction=1)
    assert lv["sl"] == 2685.0 and lv["tp1"] == 2720.0 and lv["rr"] == round(20/15, 2)
    lv_s = dynamic_levels(2700, 10, direction=-1)
    assert lv_s["sl"] == 2715.0 and lv_s["tp1"] == 2680.0
    assert dynamic_levels(2700, 0, 1)["sl"] is None


def test_circuit_breaker_halts():
    cb = CircuitBreaker(max_dd_pct=5.0)
    cb.update(10000)
    assert cb.update(9800)["halted"] is False      # هبوط 2%
    state = cb.update(9400)                          # هبوط 6% من القمة
    assert state["halted"] is True and state["dd_pct"] == 6.0
    cb.reset()
    assert cb.halted is False


def test_correlation_guard_anomaly():
    # ارتباط موجب قوي بين الذهب والدولار = شذوذ
    r = correlation_guard([1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6])
    assert r["anomaly"] is True and r["corr"] > 0.9
    # ارتباط سالب = طبيعي
    r2 = correlation_guard([1, 2, 3, 4, 5, 6], [6, 5, 4, 3, 2, 1])
    assert r2["anomaly"] is False

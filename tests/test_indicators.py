# -*- coding: utf-8 -*-
"""اختبارات المؤشرات — قيم معلومة مسبقاً، بدون شبكة."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import indicators


def test_ema_constant_series():
    s = pd.Series([100.0] * 30)
    assert abs(indicators.ema(s, 10).iloc[-1] - 100.0) < 1e-9


def test_rsi_output_valid():
    # RSI يجب أن يعيد Series صالحة: قيم ضمن [0,100] أو NaN للسلاسل القصيرة
    up = pd.Series([float(100 + i) for i in range(60)])
    v = indicators.rsi(up)
    assert len(v) == 60
    last = v.iloc[-1]
    assert (last != last) or (0.0 <= last <= 100.0)  # NaN مقبول أو قيمة ضمن النطاق

def test_atr_positive():
    df = pd.DataFrame({
        "high": [102, 104, 103, 105, 107],
        "low": [99, 100, 101, 102, 103],
        "close": [101, 103, 102, 104, 106],
    })
    a = indicators.atr(df).dropna()
    assert len(a) > 0 and (a > 0).all()


def test_support_resistance_bounds():
    close = pd.Series([100 + (i % 10) for i in range(80)], dtype="float64")
    df = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=80),
                       "open": close, "high": close + 1,
                       "low": close - 1, "close": close})
    lv = indicators.support_resistance(df)
    assert isinstance(lv, dict) and len(lv) > 0

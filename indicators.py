# -*- coding: utf-8 -*-
"""حساب المؤشرات الفنية بدون مكتبات خارجية (نقي pandas/numpy)."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    m = ema(close, fast) - ema(close, slow)
    sig = ema(m, signal)
    return m, sig, m - sig


def bollinger(close: pd.Series, n=20, k=2.0):
    mid = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return mid, mid + k * sd, mid - k * sd


def atr(df: pd.DataFrame, n=14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift()).abs(), (l - c.shift()).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def stochastic(df: pd.DataFrame, n=14, smooth=3):
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    k = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    return k, k.rolling(smooth).mean()


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["rsi"] = rsi(df["close"])
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(df["close"])
    df["bb_mid"], df["bb_up"], df["bb_low"] = bollinger(df["close"])
    df["atr"] = atr(df)
    df["stoch_k"], df["stoch_d"] = stochastic(df)
    return df


def support_resistance(df: pd.DataFrame, lookback=60):
    """دعوم ومقاومات: قيعان/قمم حديثة + Pivot كلاسيكي."""
    recent = df.tail(lookback)
    supports = sorted(set([
        round(float(recent["low"].min()), 1),
        round(float(df.tail(20)["low"].min()), 1),
    ]))
    resistances = sorted(set([
        round(float(recent["high"].max()), 1),
        round(float(df.tail(20)["high"].max()), 1),
    ]))
    last = df.iloc[-1]
    p = (last["high"] + last["low"] + last["close"]) / 3
    return {
        "supports": supports,
        "resistances": resistances,
        "pivot": round(float(p), 1),
        "r1": round(float(2 * p - last["low"]), 1),
        "s1": round(float(2 * p - last["high"]), 1),
    }

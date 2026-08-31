# -*- coding: utf-8 -*-
"""مقاييس الأداء المؤسسية — الفجوة 6 (رصد) وجزء من الفجوة 3 (تقييم صادق).

كل الدوال نقية (بدون شبكة) وتعمل على pd.Series أو قوائم.
"""
import numpy as np
import pandas as pd


def equity_from_returns(returns) -> pd.Series:
    """منحنى الإكويتي من سلسلة عوائد نسبية (مثل 0.02 = +2%)."""
    r = pd.Series(list(returns), dtype="float64")
    return (1.0 + r).cumprod() * 100.0


def max_drawdown(equity) -> float:
    """أقصى هبوط من قمة كنسبة مئوية (موجبة دائماً)."""
    eq = pd.Series(list(equity), dtype="float64")
    if eq.empty:
        return 0.0
    peak = eq.cummax()
    dd = (peak - eq) / peak * 100.0
    return float(dd.max())


def sharpe(returns, periods_per_year: int = 252) -> float:
    r = pd.Series(list(returns), dtype="float64").dropna()
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(periods_per_year))


def sortino(returns, periods_per_year: int = 252) -> float:
    r = pd.Series(list(returns), dtype="float64").dropna()
    downside = r[r < 0]
    if len(r) < 2 or downside.std() == 0 or len(downside) == 0:
        return 0.0
    return float(r.mean() / downside.std() * np.sqrt(periods_per_year))


def calmar(returns, periods_per_year: int = 252) -> float:
    r = pd.Series(list(returns), dtype="float64").dropna()
    if len(r) < 2:
        return 0.0
    eq = (1.0 + r).cumprod()
    mdd = max_drawdown(eq)
    if mdd == 0:
        return 0.0
    annual = float((eq.iloc[-1] ** (periods_per_year / len(r))) - 1.0) * 100.0
    return float(annual / mdd)


def profit_factor(pnls) -> float:
    """مجموع الأرباح / |مجموع الخسائر|."""
    p = pd.Series(list(pnls), dtype="float64")
    gains = p[p > 0].sum()
    losses = abs(p[p < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def expectancy(pnls) -> float:
    """التوقع الرياضي لكل صفقة."""
    p = pd.Series(list(pnls), dtype="float64")
    return float(p.mean()) if len(p) else 0.0


def summarize(pnls) -> dict:
    """ملخص واحد لكل المقاييس."""
    p = pd.Series(list(pnls), dtype="float64")
    rets = p / 100.0
    eq = equity_from_returns(rets)
    return {
        "trades": int(len(p)),
        "total_return_pct": round(float(eq.iloc[-1] - 100.0), 2) if len(eq) else 0.0,
        "max_drawdown_pct": round(max_drawdown(eq), 2),
        "sharpe": round(sharpe(rets), 3),
        "sortino": round(sortino(rets), 3),
        "calmar": round(calmar(rets), 3),
        "profit_factor": round(profit_factor(p), 3) if profit_factor(p) != float("inf") else "inf",
        "expectancy_pct": round(expectancy(p), 3),
    }

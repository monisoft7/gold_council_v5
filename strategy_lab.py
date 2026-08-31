# -*- coding: utf-8 -*-
"""مختبر استراتيجيات ذهب مستقلة مع تنفيذ افتتاح اليوم التالي وتقلب مستهدف."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


PERIODS = {
    "discovery_2008_2018": ("2008-01-01", "2018-12-31"),
    "validation_2019_2022": ("2019-01-01", "2022-12-31"),
    "holdout_2023_2026": ("2023-01-01", "2026-12-31"),
}


def _donchian(frame, entry=55, exit_=20):
    close, high, low = frame.close, frame.high, frame.low
    upper = high.shift(1).rolling(entry).max()
    lower = low.shift(1).rolling(entry).min()
    exit_low = low.shift(1).rolling(exit_).min()
    exit_high = high.shift(1).rolling(exit_).max()
    state, out = 0.0, []
    for i in range(len(frame)):
        if state <= 0 and pd.notna(upper.iloc[i]) and close.iloc[i] > upper.iloc[i]: state = 1.0
        elif state >= 0 and pd.notna(lower.iloc[i]) and close.iloc[i] < lower.iloc[i]: state = -1.0
        elif state > 0 and pd.notna(exit_low.iloc[i]) and close.iloc[i] < exit_low.iloc[i]: state = 0.0
        elif state < 0 and pd.notna(exit_high.iloc[i]) and close.iloc[i] > exit_high.iloc[i]: state = 0.0
        out.append(state)
    return pd.Series(out, index=frame.index)


def _bollinger(frame, window=50, width=2.0):
    close = frame.close
    mean, std = close.rolling(window).mean(), close.rolling(window).std()
    raw = pd.Series(np.nan, index=frame.index)
    raw[close > mean + width * std] = 1.0
    raw[close < mean - width * std] = -1.0
    raw[(close - mean).abs() < 0.25 * std] = 0.0
    return raw.ffill().fillna(0.0)


def _rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/window, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1/window, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def signals(frame):
    close = frame.close
    momentum = pd.concat([(close / close.shift(h) - 1).apply(np.sign)
                          for h in (20, 60, 120, 252)], axis=1).mean(axis=1).fillna(0)
    ma, std = close.rolling(50).mean(), close.rolling(50).std()
    rsi = _rsi(close)
    ranging = ((close / ma - 1).abs() < 0.04) & (std / ma < (std / ma).rolling(252).median())
    mr = pd.Series(0.0, index=frame.index)
    mr[ranging & (rsi < 30)] = 1.0
    mr[ranging & (rsi > 70)] = -1.0
    bollinger = _bollinger(frame)
    return {
        "tsmom_multi_horizon": momentum,
        "tsmom_long_flat": momentum.clip(lower=0),
        "donchian_55_20": _donchian(frame),
        "bollinger_breakout_50": bollinger,
        "trend_breakout_ensemble": (0.5 * momentum + 0.5 * bollinger).clip(-1, 1),
        "regime_mean_reversion": mr,
    }


def backtest(frame, signal, cost_bps=5.0, target_vol=0.10):
    open_ret = frame.open.shift(-1) / frame.open - 1
    realized = open_ret.rolling(20).std().shift(1) * np.sqrt(252)
    leverage = (target_vol / realized).clip(upper=1.0).replace([np.inf, -np.inf], np.nan).fillna(0)
    position = signal.shift(1).fillna(0) * leverage
    turnover = position.diff().abs().fillna(position.abs())
    net = (position * open_ret - turnover * cost_bps / 10000).fillna(0)
    return pd.DataFrame({"time": frame.time, "position": position,
                         "turnover": turnover, "net_return": net})


def metrics(result):
    returns = result.net_return
    if len(returns) < 2: return {"days": len(returns)}
    equity = (1 + returns).cumprod()
    years = max(len(returns) / 252, 1 / 252)
    cagr = equity.iloc[-1] ** (1 / years) - 1
    drawdown = equity / equity.cummax() - 1
    std = returns.std()
    sharpe = returns.mean() / std * np.sqrt(252) if std > 0 else 0
    downside = returns[returns < 0].std()
    sortino = returns.mean() / downside * np.sqrt(252) if downside > 0 else 0
    positive, negative = returns[returns > 0].sum(), abs(returns[returns < 0].sum())
    return {"days": len(result), "total_return_pct": round((equity.iloc[-1]-1)*100, 2),
            "cagr_pct": round(cagr*100, 2), "max_drawdown_pct": round(abs(drawdown.min())*100, 2),
            "sharpe": round(sharpe, 3), "sortino": round(sortino, 3),
            "profit_factor": round(positive/negative, 3) if negative else None,
            "rebalances": int((result.position.diff().abs() > 0).sum()),
            "exposure_pct": round((result.position.abs() > 0).mean()*100, 1)}


def run(prices, cost_bps=5.0, target_vol=0.10):
    frame = pd.read_csv(prices)
    frame.time = pd.to_datetime(frame.time, errors="coerce", utc=True)
    frame = frame.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time")
    report = {"assumptions": {"execution": "next session open", "cost_bps_per_turnover": cost_bps,
                               "target_annual_vol": target_vol, "max_leverage": 1.0}, "strategies": {}}
    for name, signal in signals(frame).items():
        result = backtest(frame, signal, cost_bps, target_vol)
        item = {"all": metrics(result)}
        for period, (start, end) in PERIODS.items():
            mask = result.time.between(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"))
            item[period] = metrics(result.loc[mask].reset_index(drop=True))
        report["strategies"][name] = item
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--target-vol", type=float, default=0.10)
    parser.add_argument("--out", default="data_cache/strategy_lab_2008_2026.json")
    args = parser.parse_args()
    report = run(args.prices, args.cost_bps, args.target_vol)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()

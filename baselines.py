# -*- coding: utf-8 -*-
"""مراجع بسيطة يجب أن يتفوق عليها المجلس بعد التكلفة."""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

import indicators
import metrics


def signals(df: pd.DataFrame) -> dict[str, pd.Series]:
    x = indicators.add_all(df)
    close = x["close"]
    return {
        "buy_hold": pd.Series(1.0, index=x.index),
        "ema_20_50": (x["ema20"] > x["ema50"]).astype(float),
        "momentum_20": (close.pct_change(20) > 0).astype(float),
        "rsi_mean_reversion": pd.Series(
            np.where(x["rsi"] < 35, 1.0, np.where(x["rsi"] > 65, 0.0, np.nan)),
            index=x.index).ffill().fillna(0.0),
    }


def evaluate(df: pd.DataFrame, cost_bps=5.0) -> dict:
    market = df["close"].pct_change().fillna(0.0)
    report = {}
    for name, raw_signal in signals(df).items():
        # إشارة إغلاق t لا تنفذ قبل عائد t+1.
        position = raw_signal.shift(1).fillna(0.0)
        turnover = position.diff().abs().fillna(position.abs())
        returns = position * market - turnover * (cost_bps / 10000.0)
        summary = metrics.summarize((returns * 100).tolist())
        summary["exposure_pct"] = round(float(position.mean() * 100), 1)
        summary["transactions"] = int((turnover > 0).sum())
        report[name] = summary
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="gold_3y_daily.csv")
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--out", default="data_cache/baseline_report.json")
    args = parser.parse_args()
    frame = pd.read_csv(args.prices)
    result = evaluate(frame, args.cost_bps)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

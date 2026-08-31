# -*- coding: utf-8 -*-
"""يقيس الأداء داخل أنظمة الذهب بدل إخفائه بمتوسط سوق صاعد."""
from __future__ import annotations

import argparse
import json

import pandas as pd

import baselines
import indicators
import metrics


def classify(df: pd.DataFrame) -> pd.Series:
    x = indicators.add_all(df)
    slope = x["ema200"].pct_change(20)
    gap = x["close"] / x["ema200"] - 1
    regime = pd.Series("sideways", index=x.index)
    regime[(gap > 0.02) & (slope > 0.005)] = "bull"
    regime[(gap < -0.02) & (slope < -0.005)] = "bear"
    return regime


def analyze(df: pd.DataFrame, cost_bps=5.0) -> dict:
    market = df["close"].pct_change().fillna(0.0)
    regime = classify(df)
    output = {"regime_days": regime.value_counts().to_dict(), "strategies": {}}
    for name, signal in baselines.signals(df).items():
        position = signal.shift(1).fillna(0.0)
        turnover = position.diff().abs().fillna(position.abs())
        returns = position * market - turnover * cost_bps / 10000.0
        output["strategies"][name] = {}
        for label in ("bull", "bear", "sideways"):
            selected = returns[regime == label]
            summary = metrics.summarize((selected * 100).tolist())
            output["strategies"][name][label] = {
                "days": int(len(selected)),
                "total_return_pct": summary["total_return_pct"],
                "max_drawdown_pct": summary["max_drawdown_pct"],
                "sharpe": summary["sharpe"],
            }
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--out", default="data_cache/regime_report.json")
    args = parser.parse_args()
    report = analyze(pd.read_csv(args.prices))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

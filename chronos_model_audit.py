# -*- coding: utf-8 -*-
"""تدقيق point-in-time مستقل لوكيل Chronos قبل منحه أي وزن في المجلس."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import chronos_foundation_agent as foundation


PERIODS = {
    "discovery_2008_2018": ("2008-01-01", "2018-12-31"),
    "validation_2019_2022": ("2019-01-01", "2022-12-31"),
    "holdout_2023_2026": ("2023-01-01", "2026-12-31"),
}


def _metrics(rows, start, end):
    selected = [r for r in rows if start <= r["day"] <= end]
    directional = [r for r in selected if r["direction"] != 0]
    correct = [r for r in directional if r["correct"]]
    profits = [r["strategy_return_pct"] for r in directional
               if r["strategy_return_pct"] > 0]
    losses = [r["strategy_return_pct"] for r in directional
              if r["strategy_return_pct"] <= 0]
    gross_loss = abs(sum(losses))
    return {
        "observations": len(selected),
        "directional": len(directional),
        "directional_accuracy_pct": (
            round(100 * len(correct) / len(directional), 1) if directional else None
        ),
        "mean_strategy_return_pct": (
            round(sum(r["strategy_return_pct"] for r in directional) / len(directional), 3)
            if directional else None
        ),
        "sum_strategy_return_pct": round(sum(profits) + sum(losses), 3),
        "profit_factor": round(sum(profits) / gross_loss, 3) if gross_loss else None,
    }


def run(prices, pipeline, *, step=20, horizon=5, threshold=10):
    frame = prices.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    frame = frame.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    rows = []
    for i in range(512, len(frame) - horizon - 1, step):
        report = foundation.chronos_foundation_agent(
            frame.iloc[:i + 1], pipeline=pipeline, horizon=horizon
        )
        if not report.flags.get("available"):
            continue
        entry = float(frame.iloc[i + 1]["open"])
        exit_price = float(frame.iloc[i + horizon]["close"])
        realized = exit_price / entry - 1.0
        direction = 1 if report.score > threshold else -1 if report.score < -threshold else 0
        rows.append({
            "day": frame.iloc[i]["time"].strftime("%Y-%m-%d"),
            "score": report.score,
            "direction": direction,
            "realized_return_pct": round(realized * 100, 4),
            # 0.05% لكل جانب، متسق مع backtester_v5.
            "strategy_return_pct": round(direction * realized * 100 - 0.1, 4)
            if direction else 0.0,
            "correct": bool(direction and direction * realized > 0),
        })
    return {
        "method": "fixed zero-shot model; next-session execution; no council weight",
        "model": foundation.DEFAULT_MODEL,
        "step": step,
        "horizon": horizon,
        "threshold": threshold,
        "all": _metrics(rows, "0000-01-01", "9999-12-31"),
        **{name: _metrics(rows, start, end)
           for name, (start, end) in PERIODS.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--step", type=int, default=20)
    parser.add_argument("--horizon", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=10)
    parser.add_argument("--out", default="data_cache/chronos_audit.json")
    args = parser.parse_args()
    from chronos import BaseChronosPipeline
    pipeline = BaseChronosPipeline.from_pretrained(
        foundation.DEFAULT_MODEL, device_map="cpu"
    )
    report = run(pd.read_csv(args.prices), pipeline, step=args.step,
                 horizon=args.horizon, threshold=args.threshold)
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

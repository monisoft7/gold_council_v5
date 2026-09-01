# -*- coding: utf-8 -*-
"""Audit event-impact labels against strictly subsequent gold sessions."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd


def audit(events: pd.DataFrame, prices: pd.DataFrame,
          horizons=(1, 3, 7)) -> tuple[pd.DataFrame, dict]:
    events = events.copy()
    prices = prices.copy()
    events["available_at"] = pd.to_datetime(events["available_at"], utc=True,
                                              errors="coerce")
    prices["time"] = pd.to_datetime(prices["time"], utc=True, errors="coerce")
    events = events.dropna(subset=["available_at"]).sort_values("available_at")
    prices = prices.dropna(subset=["time", "open", "close"]).sort_values("time")
    price_times = prices["time"].tolist()
    records = []
    for _, event in events.iterrows():
        # side='right' guarantees the entry bar begins strictly after availability.
        entry_index = prices["time"].searchsorted(event["available_at"], side="right")
        if entry_index >= len(prices):
            continue
        direction = {"bullish": 1, "bearish": -1}.get(str(event.get("gold_impact")), 0)
        if not direction:
            continue
        entry = float(prices.iloc[entry_index]["open"])
        row = {"available_at": event["available_at"].isoformat(),
               "entry_time": price_times[entry_index].isoformat(),
               "impact": event["gold_impact"], "direction": direction,
               "entry": entry, "confidence": float(event.get("confidence", 0))}
        if "official_event_type" in event.index:
            row["official_event_type"] = event.get("official_event_type")
        for horizon in horizons:
            exit_index = entry_index + horizon - 1
            if exit_index >= len(prices):
                row[f"return_{horizon}s"] = None
                row[f"correct_{horizon}s"] = None
                continue
            market_return = (float(prices.iloc[exit_index]["close"]) / entry - 1) * 100
            row[f"return_{horizon}s"] = market_return
            row[f"correct_{horizon}s"] = int(direction * market_return > 0)
        records.append(row)
    detail = pd.DataFrame(records)
    _, summary = audit_summary(detail, horizons)
    if not detail.empty and "official_event_type" in detail.columns:
        summary["by_event_type"] = {}
        for event_type, group in detail.groupby("official_event_type"):
            _, group_summary = audit_summary(group, horizons)
            summary["by_event_type"][str(event_type)] = group_summary
    return detail, summary


def audit_summary(detail: pd.DataFrame, horizons=(1, 3, 7)) -> tuple[pd.DataFrame, dict]:
    """Summarize already-computed detail without recursively grouping it."""
    clean = detail.drop(columns=["official_event_type"], errors="ignore")
    summary = {"signals": len(clean), "horizons": {}}
    for horizon in horizons:
        correct = pd.to_numeric(
            clean.get(f"correct_{horizon}s", pd.Series(dtype=float)), errors="coerce"
        )
        returns = pd.to_numeric(
            clean.get(f"return_{horizon}s", pd.Series(dtype=float)), errors="coerce"
        )
        directed = returns * clean.get("direction", pd.Series(dtype=float))
        valid = correct.notna()
        directed_valid = directed[valid].dropna()
        wins = float((correct[valid] == 1).sum())
        observations = int(valid.sum())
        if observations:
            z = 1.96
            rate = wins / observations
            denominator = 1 + z * z / observations
            center = (rate + z * z / (2 * observations)) / denominator
            margin = (z * math.sqrt(rate * (1 - rate) / observations +
                                    z * z / (4 * observations ** 2)) /
                      denominator)
            interval = [round((center - margin) * 100, 2),
                        round((center + margin) * 100, 2)]
        else:
            interval = [None, None]
        gross_profit = directed_valid[directed_valid > 0].sum()
        gross_loss = -directed_valid[directed_valid < 0].sum()
        summary["horizons"][str(horizon)] = {
            "observations": observations,
            "directional_accuracy_pct": round(float(correct[valid].mean() * 100), 2)
            if valid.any() else None,
            "accuracy_wilson_95_pct": interval,
            "mean_directed_return_pct": round(float(directed[valid].mean()), 4)
            if valid.any() else None,
            "median_directed_return_pct": round(float(directed_valid.median()), 4)
            if not directed_valid.empty else None,
            "profit_factor": round(float(gross_profit / gross_loss), 4)
            if gross_loss > 0 else None,
        }
    return detail, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default="data_cache/gold_news_events.csv")
    parser.add_argument("--prices", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--detail", default="data_cache/news_event_audit.csv")
    parser.add_argument("--report", default="data_cache/news_event_audit.json")
    args = parser.parse_args()
    detail, summary = audit(pd.read_csv(args.events), pd.read_csv(args.prices))
    detail_path, report_path = Path(args.detail), Path(args.report)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(detail_path, index=False)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

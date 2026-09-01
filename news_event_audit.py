# -*- coding: utf-8 -*-
"""Audit event-impact labels against strictly subsequent gold sessions."""
from __future__ import annotations

import argparse
import json
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
    summary = {"signals": len(detail), "horizons": {}}
    for horizon in horizons:
        correct = pd.to_numeric(
            detail.get(f"correct_{horizon}s", pd.Series(dtype=float)),
            errors="coerce",
        )
        returns = pd.to_numeric(
            detail.get(f"return_{horizon}s", pd.Series(dtype=float)),
            errors="coerce",
        )
        directed = returns * detail.get("direction", pd.Series(dtype=float))
        valid = correct.notna()
        summary["horizons"][str(horizon)] = {
            "observations": int(valid.sum()),
            "directional_accuracy_pct": round(float(correct[valid].mean() * 100), 2)
            if valid.any() else None,
            "mean_directed_return_pct": round(float(directed[valid].mean()), 4)
            if valid.any() else None,
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

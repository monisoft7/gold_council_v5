# -*- coding: utf-8 -*-
"""Convert historical headlines into checkpointed daily event observations."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

import event_intelligence
import llm_gateway


FIELDS = ("available_at", "event_date", "event_type", "gold_impact", "magnitude",
          "horizon_hours", "novelty", "confidence", "rationale", "provider",
          "model", "headline_count")


def build(source: Path, output: Path, *, max_days=None) -> list[dict]:
    news = pd.read_csv(source)
    news["time"] = pd.to_datetime(news["time"], utc=True, errors="coerce")
    news = news.dropna(subset=["time", "title"]).sort_values("time")
    existing = []
    if output.exists():
        with output.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    completed = {row["event_date"] for row in existing}
    selected = llm_gateway.settings()
    if selected is None:
        raise RuntimeError("No configured LLM provider")
    added = 0
    attempted = 0
    for event_date, group in news.groupby(news["time"].dt.date, sort=True):
        day = event_date.isoformat()
        if day in completed:
            continue
        if max_days is not None and attempted >= max_days:
            break
        attempted += 1
        result = event_intelligence.analyze(
            group["title"].tolist(), selected=selected, allow_network=True
        )
        if result["status"] != "ok":
            print(f"SKIP {day}: {result['status']}", flush=True)
            continue
        value = result["analysis"]
        existing.append({
            "available_at": group["time"].max().isoformat(),
            "event_date": day,
            **{key: value[key] for key in ("event_type", "gold_impact", "magnitude",
                                            "horizon_hours", "novelty", "confidence",
                                            "rationale")},
            "provider": result["provider"], "model": result["model"],
            "headline_count": len(group),
        })
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(existing)
        added += 1
        print(f"[{added}] {day} headlines={len(group)}", flush=True)
    return existing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data_cache/gold_news_history.csv")
    parser.add_argument("--output", default="data_cache/gold_news_events.csv")
    parser.add_argument("--max-days", type=int)
    args = parser.parse_args()
    rows = build(Path(args.source), Path(args.output), max_days=args.max_days)
    print(f"DONE rows={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()

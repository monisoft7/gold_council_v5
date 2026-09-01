# -*- coding: utf-8 -*-
"""Build and label a deterministic CPI/NFP/FOMC point-in-time news sample."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pandas as pd

import event_intelligence
import llm_gateway


TYPE_TERMS = {
    "CPI": ("inflation", " cpi", "consumer price", "price pressures"),
    "NFP": ("payroll", "jobs report", "employment", "unemployment", "labor market"),
    "FOMC": ("federal reserve", " fed ", "powell", "interest rate", "rate hike",
             "rate cut", "monetary policy"),
}
GOLD_TERMS = ("gold", "bullion", "xau", "dollar", "treasury", "yield")
OUTPUT_FIELDS = (
    "available_at", "event_date", "official_event_type", "official_event_time",
    "event_type", "gold_impact", "magnitude", "horizon_hours", "novelty",
    "confidence", "rationale", "provider", "model", "headline_count",
)


def normalize_event_type(section: str, title: str) -> str | None:
    text = f"{section} {title}".casefold()
    if "cpi" in text or "تضخم" in text:
        return "CPI"
    if "nfp" in text or "payroll" in text or "وظائف" in text:
        return "NFP"
    if "fomc" in text or "فائدة" in text or "federal reserve" in text:
        return "FOMC"
    return None


def _matches(title: str, event_type: str) -> bool:
    text = f" {title.casefold()} "
    return any(term in text for term in TYPE_TERMS[event_type] + GOLD_TERMS)


def build_sample(events: pd.DataFrame, news: pd.DataFrame, *, start="2023-01-01",
                 end="2025-04-15", per_type=8) -> list[dict]:
    events = events.copy(); news = news.copy()
    events["event_time"] = pd.to_datetime(events["time"], utc=True, errors="coerce")
    news["available_at"] = pd.to_datetime(news["time"], utc=True, errors="coerce")
    if "source_date" in news:
        news["source_day"] = pd.to_datetime(news["source_date"], errors="coerce").dt.date
    else:
        news["source_day"] = (news["available_at"] - pd.Timedelta(days=1)).dt.date
    events["official_event_type"] = [
        normalize_event_type(section, title)
        for section, title in zip(events["section"], events["title"])
    ]
    start_at, end_at = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    events = events[
        events["event_time"].between(start_at, end_at, inclusive="left") &
        events["official_event_type"].notna()
    ].sort_values("event_time")
    observations = []
    for _, event in events.iterrows():
        event_type = event["official_event_type"]
        day = event["event_time"].date()
        candidates = news[news["source_day"] == day]
        titles = [str(title) for title in candidates["title"]
                  if _matches(str(title), event_type)]
        if not titles:
            continue
        availability = candidates[candidates["title"].isin(titles)]["available_at"].max()
        observations.append({
            "official_event_time": event["event_time"].isoformat(),
            "official_event_type": event_type,
            "available_at": availability.isoformat(),
            "headlines": sorted(set(titles))[:24],
        })
    selected = []
    for event_type in TYPE_TERMS:
        group = [item for item in observations if item["official_event_type"] == event_type]
        if len(group) <= per_type:
            selected.extend(group)
            continue
        indexes = [round(i * (len(group) - 1) / (per_type - 1))
                   for i in range(per_type)] if per_type > 1 else [len(group) - 1]
        selected.extend(group[index] for index in sorted(set(indexes)))
    return sorted(selected, key=lambda item: item["official_event_time"])


def label_sample(sample: list[dict], output: Path, *, provider="Groq",
                 max_samples=None) -> list[dict]:
    existing = []
    if output.exists():
        with output.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    completed = {row["official_event_time"] for row in existing}
    selected = llm_gateway.settings_for(provider)
    if selected is None:
        raise RuntimeError(f"provider not configured: {provider}")
    attempted = 0
    for item in sample:
        if item["official_event_time"] in completed:
            continue
        if max_samples is not None and attempted >= max_samples:
            break
        attempted += 1
        result = event_intelligence.analyze(
            item["headlines"], selected=selected, allow_network=True,
        )
        if result["status"] != "ok":
            detail = ""
            if result["status"] == "http_error":
                detail = (f" HTTP {result.get('http_status')} "
                          f"{result.get('error_message', '')}")
            print(f"SKIP {item['official_event_time']}: {result['status']}{detail}",
                  flush=True)
            if result["status"] == "rate_limited":
                print("STOP provider rate limit; resume later from checkpoint", flush=True)
                break
            continue
        value = result["analysis"]
        row = {
            "available_at": item["available_at"],
            "event_date": item["official_event_time"][:10],
            "official_event_type": item["official_event_type"],
            "official_event_time": item["official_event_time"],
            **{key: value[key] for key in ("event_type", "gold_impact", "magnitude",
                                            "horizon_hours", "novelty", "confidence",
                                            "rationale")},
            "provider": result["provider"], "model": result["model"],
            "headline_count": len(item["headlines"]),
        }
        existing.append(row)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
            writer.writeheader(); writer.writerows(existing)
        print(f"[{attempted}] {row['event_date']} {row['official_event_type']} "
              f"impact={row['gold_impact']}", flush=True)
    return existing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default="data_cache/events_2008_2026.csv")
    parser.add_argument("--news", default="data_cache/gold_news_wsj_2019_2025.csv")
    parser.add_argument("--output", default="data_cache/official_event_news_labels.csv")
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2025-04-15")
    parser.add_argument("--per-type", type=int, default=8)
    parser.add_argument("--provider", default="Groq",
                        choices=("Groq", "B.AI", "OpenRouter", "Gemini"))
    parser.add_argument("--max-samples", type=int)
    args = parser.parse_args()
    sample = build_sample(pd.read_csv(args.events), pd.read_csv(args.news),
                          start=args.start, end=args.end, per_type=args.per_type)
    print("sample=" + json.dumps({key: sum(item["official_event_type"] == key
                                           for item in sample)
                                  for key in TYPE_TERMS}, sort_keys=True))
    rows = label_sample(sample, Path(args.output), provider=args.provider,
                        max_samples=args.max_samples)
    print(f"DONE labels={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()

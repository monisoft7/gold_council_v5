# -*- coding: utf-8 -*-
"""Convert the local Kaggle precious-metals dataset to point-in-time news rows.

The source contains a publication date but no intraday timestamp. To avoid lookahead,
every headline is conservatively made available at 00:00 UTC on the following day.
"""
from __future__ import annotations

import argparse
import csv
from datetime import timedelta, timezone
from pathlib import Path
import re

import pandas as pd


CAUSAL_TERMS = (
    "gold", "bullion", "federal reserve", " fed ", "powell", "interest rate",
    "rate cut", "rate hike", "inflation", " cpi", "payroll", "jobs report",
    "unemployment", "treasury", "bond yield", "yields", "u.s. dollar",
    "dollar rises", "dollar falls", "dollar slides", "recession", "tariff",
    "trade war", "sanction", "war ", "invasion", "cease-fire", "ceasefire",
    "central bank", "safe haven", "safe-haven",
)
FIELDS = ("time", "title", "source", "section", "url", "language",
          "source_date", "timing_precision")


def is_causal(title: str) -> bool:
    padded = f" {title.casefold()} "
    return any(term in padded for term in CAUSAL_TERMS)


def convert(source: Path, output: Path, *, start="2019-01-01",
            end="2025-04-15") -> list[dict]:
    frame = pd.read_csv(source, sep=";")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp", "headlines"])
    frame = frame[(frame["timestamp"] >= pd.Timestamp(start)) &
                  (frame["timestamp"] < pd.Timestamp(end))]
    rows, seen = [], set()
    for _, item in frame.sort_values("timestamp").iterrows():
        source_date = item["timestamp"].date()
        available = pd.Timestamp(source_date + timedelta(days=1), tz=timezone.utc)
        for headline in re.split(r"\s+/\s+", str(item["headlines"])):
            title = " ".join(headline.split())
            key = source_date.isoformat(), title.casefold()
            if not title or key in seen or not is_causal(title):
                continue
            seen.add(key)
            rows.append({
                "time": available.isoformat(), "title": title,
                "source": "WSJ via Kaggle", "section": "macro_gold_causal",
                "url": "", "language": "English",
                "source_date": source_date.isoformat(),
                "timing_precision": "next_day_conservative",
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data_cache/final_gold_data.csv")
    parser.add_argument("--output", default="data_cache/gold_news_wsj_2019_2025.csv")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default="2025-04-15")
    args = parser.parse_args()
    rows = convert(Path(args.source), Path(args.output), start=args.start, end=args.end)
    print(f"DONE rows={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()

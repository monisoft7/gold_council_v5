# -*- coding: utf-8 -*-
"""Point-in-time Alpha Vantage NEWS_SENTIMENT collector with safe errors."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import requests

from env_loader import env


ENDPOINT = "https://www.alphavantage.co/query"
FIELDS = ("time", "title", "source", "section", "url", "summary",
          "overall_sentiment_score", "overall_sentiment_label", "provider")
GOLD_CAUSAL = (
    "gold", "bullion", "xau", "federal reserve", " fed ", "powell",
    "interest rate", "inflation", " cpi", "payroll", "jobs report",
    "treasury", "bond yield", "real yield", "u.s. dollar", "dollar index",
    "central bank", "safe haven", "recession", "ceasefire", "invasion",
)


def _stamp(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _is_relevant(item: dict) -> bool:
    text = f" {(item.get('title') or '')} {(item.get('summary') or '')} ".casefold()
    return any(term in text for term in GOLD_CAUSAL)


def fetch_window(start: datetime, end: datetime, *, limit=1000,
                 timeout=60) -> list[dict]:
    api_key = env.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise RuntimeError("missing ALPHA_VANTAGE_API_KEY")
    response = requests.get(ENDPOINT, params={
        "function": "NEWS_SENTIMENT",
        "topics": "economy_monetary,financial_markets,economy_macro",
        "time_from": start.strftime("%Y%m%dT%H%M"),
        "time_to": end.strftime("%Y%m%dT%H%M"),
        "sort": "EARLIEST", "limit": limit, "apikey": api_key,
    }, timeout=timeout)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Alpha Vantage HTTP {response.status_code}: invalid JSON") from exc
    if response.status_code != 200:
        raise RuntimeError(f"Alpha Vantage HTTP {response.status_code}")
    problem = payload.get("Error Message") or payload.get("Information") or payload.get("Note")
    if problem:
        raise RuntimeError(f"Alpha Vantage API: {str(problem)[:240]}")
    output = []
    for item in payload.get("feed", []):
        published = _stamp(item.get("time_published"))
        if not published or not (start <= published < end) or not _is_relevant(item):
            continue
        output.append({
            "time": published.isoformat(), "title": item.get("title", "").strip(),
            "source": item.get("source") or "Alpha Vantage",
            "section": "gold_macro_news", "url": item.get("url") or "",
            "summary": item.get("summary") or "",
            "overall_sentiment_score": item.get("overall_sentiment_score", ""),
            "overall_sentiment_label": item.get("overall_sentiment_label", ""),
            "provider": "Alpha Vantage",
        })
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="UTC ISO timestamp")
    parser.add_argument("--end", required=True, help="UTC ISO timestamp")
    parser.add_argument("--output")
    args = parser.parse_args()
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    rows = fetch_window(start, end)
    print(f"relevant={len(rows)}")
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader(); writer.writerows(rows)
        print(f"output={path}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Build a reproducible, point-in-time gold-news archive from GDELT DOC 2.0.

The collector is resumable and writes only publication-time facts. LLM labels are
deliberately produced by a separate offline step so a backtest never calls a live
model or sees a later article.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re
import time
from urllib.parse import urlparse

import requests


ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY = (
    '("gold price" OR XAUUSD OR "gold futures") '
    '(Federal Reserve OR inflation OR CPI OR dollar OR yields OR war OR '
    '"central bank" OR ETF OR bullion OR jobs OR payrolls)'
)
FIELDS = ("time", "title", "source", "section", "url", "language")
HEADERS = {"User-Agent": "gold-council-research/1.0"}


def _parse_date(value: str) -> datetime | None:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _key(row: dict) -> tuple[str, str]:
    title = re.sub(r"\W+", " ", row.get("title", "").casefold()).strip()
    return row.get("time", "")[:10], title


def fetch_window(start: datetime, end: datetime, *, timeout=60, retries=4) -> list[dict]:
    params = {
        "query": QUERY,
        "mode": "artlist",
        "maxrecords": 250,
        "format": "csv",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }
    for attempt in range(retries + 1):
        try:
            response = requests.get(ENDPOINT, params=params, headers=HEADERS,
                                    timeout=timeout)
            if getattr(response, "status_code", 200) == 429 and attempt < retries:
                retry_after = response.headers.get("Retry-After", "")
                delay = float(retry_after) if retry_after.isdigit() else 30 * (attempt + 1)
                print(f"GDELT rate limit; retrying in {delay:.0f}s", flush=True)
                time.sleep(delay)
                continue
            response.raise_for_status()
            rows = csv.DictReader(io.StringIO(response.text.lstrip("\ufeff")))
            output = []
            for raw in rows:
                published = _parse_date(raw.get("Date", ""))
                title = (raw.get("Title") or "").strip()
                url = (raw.get("URL") or "").strip()
                if not published or not title or not (start <= published < end):
                    continue
                output.append({
                    "time": published.isoformat(),
                    "title": title,
                    "source": urlparse(url).netloc.removeprefix("www.") or "GDELT",
                    "section": "gold_causal_news",
                    "url": url,
                    "language": (raw.get("Language") or "").strip(),
                })
            return output
        except (requests.RequestException, csv.Error):
            if attempt == retries:
                raise
            time.sleep(max(2 ** attempt, 5))
    return []


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda item: item["time"]))


def build(start: datetime, end: datetime, output: Path, *, window_days=14,
          pause=1.0, max_windows=None) -> list[dict]:
    existing = _read_existing(output)
    by_key = {_key(row): row for row in existing if row.get("title")}
    state_path = output.with_suffix(output.suffix + ".state.json")
    try:
        completed = set(json.loads(state_path.read_text(encoding="utf-8"))["completed"])
    except Exception:
        completed = set()
    cursor = start
    windows = 0
    while cursor < end and (max_windows is None or windows < max_windows):
        window_end = min(cursor + timedelta(days=window_days), end)
        window_id = f"{cursor.isoformat()}..{window_end.isoformat()}"
        if window_id in completed:
            cursor = window_end
            continue
        fetched = fetch_window(cursor, window_end)
        for row in fetched:
            by_key.setdefault(_key(row), row)
        windows += 1
        _write(output, list(by_key.values()))
        completed.add(window_id)
        state_path.write_text(
            json.dumps({"query": QUERY, "completed": sorted(completed)}, indent=2),
            encoding="utf-8",
        )
        print(f"[{windows}] {cursor.date()}..{window_end.date()} "
              f"fetched={len(fetched)} total={len(by_key)}", flush=True)
        if len(fetched) >= 250:
            print("WARNING maxrecords reached; use a smaller --window-days value",
                  flush=True)
        cursor = window_end
        if cursor < end and pause:
            time.sleep(pause)
    return list(by_key.values())


def _utc_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--end", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--output", default="data_cache/gold_news_history.csv")
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--pause", type=float, default=10.0)
    parser.add_argument("--max-windows", type=int)
    args = parser.parse_args()
    rows = build(_utc_date(args.start), _utc_date(args.end), Path(args.output),
                 window_days=args.window_days, pause=args.pause,
                 max_windows=args.max_windows)
    print(f"DONE rows={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()

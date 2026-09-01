# -*- coding: utf-8 -*-
"""اجمع لقطة التقويم الأسبوعي في أرشيف append-only قابل للتدقيق."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from economic_surprise_agent import fetch_weekly_calendar, merge_snapshots


def update_snapshot(output="data_cache/economic_calendar_snapshots.csv", *,
                    usd_only=True, high_impact_only=False) -> pd.DataFrame:
    """Fetch once and atomically extend the point-in-time snapshot file."""
    target = Path(output)
    current = fetch_weekly_calendar()
    if usd_only:
        current = current[current["country"] == "USD"]
    if high_impact_only:
        current = current[current["impact"].str.casefold() == "high"]
    existing = pd.read_csv(target) if target.exists() else None
    merged = merge_snapshots(existing, current)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    merged.to_csv(temporary, index=False, encoding="utf-8")
    temporary.replace(target)
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data_cache/economic_calendar_snapshots.csv")
    parser.add_argument("--usd-only", action="store_true", default=True)
    parser.add_argument("--high-impact-only", action="store_true")
    args = parser.parse_args()
    target = Path(args.output)
    merged = update_snapshot(target, usd_only=args.usd_only,
                             high_impact_only=args.high_impact_only)
    completed = int(merged.get("actual_available_at", pd.Series(dtype=object)).notna().sum())
    print(f"saved snapshots={len(merged)} completed={completed} to {target}")


if __name__ == "__main__":
    main()

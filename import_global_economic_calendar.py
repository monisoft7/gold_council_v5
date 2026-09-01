# -*- coding: utf-8 -*-
"""استيراد أحداث الذهب الأساسية من مجموعة Global Economic Calendar.

المجموعة مرخصة CC BY-NC-SA 4.0. الخام يبقى في ``data_cache`` ولا يُرفع.
لا تحتوي المجموعة وقت التقاط Actual؛ نفترض لأغراض دراسة الحدث أنه أصبح
متاحاً عند وقت الإصدار المجدول، ونوسم هذا الافتراض صراحةً.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from economic_surprise_agent import calculate_surprise
from mt5_event_history import canonical_release_time


SOURCE = "Kaggle Global Economic Calendar (CC BY-NC-SA 4.0)"


def classify_event(title: str) -> str | None:
    text = title.casefold().strip()
    if text.startswith("nonfarm payrolls"):
        return "NFP"
    if text.startswith("core cpi") or text.startswith("cpi ("):
        return "CPI"
    if text.startswith("fed interest rate decision"):
        return "FOMC"
    return None


def import_calendar(raw: pd.DataFrame, *, start="2025-01-01",
                    end="2025-10-01") -> pd.DataFrame:
    frame = raw.copy()
    frame["event_type"] = frame["event"].astype(str).map(classify_event)
    frame = frame[
        (frame["currency"].astype(str).str.upper() == "USD")
        & (frame["importance"].astype(str).str.casefold() == "high")
        & frame["event_type"].notna()
    ].copy()
    frame["source_time"] = pd.to_datetime(
        frame["date"].astype(str) + " " + frame["time"].astype(str),
        dayfirst=True, errors="coerce", utc=True,
    )
    frame = frame.dropna(subset=["source_time"])
    frame["release_time"] = [
        canonical_release_time(value, kind)
        for value, kind in zip(frame["source_time"], frame["event_type"])
    ]
    start_at, end_at = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    frame = frame[frame["release_time"].between(start_at, end_at, inclusive="left")]
    rows = []
    for row in frame.itertuples():
        calc = calculate_surprise(row.actual, row.forecast, row.previous, row.event)
        if calc is None:
            continue
        rows.append({
            "source": SOURCE, "license": "CC BY-NC-SA 4.0",
            "country": "USD", "impact": "High", "title": row.event,
            "event_type": row.event_type, "release_time": row.release_time,
            "source_time": row.source_time, "actual": row.actual,
            "forecast": row.forecast, "previous": row.previous,
            # هذا أفضل افتراض متاح لدراسة M5، وليس timestamp من vendor.
            "actual_available_at": row.release_time,
            "forecast_available_at": row.release_time - pd.Timedelta(microseconds=1),
            "fetched_at": row.release_time,
            "availability_assumption": "actual_at_scheduled_release_no_capture_timestamp",
            **calc,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["source_time_delta_minutes"] = (
        pd.to_datetime(out["source_time"], utc=True)
        - pd.to_datetime(out["release_time"], utc=True)
    ).dt.total_seconds() / 60
    return (out.sort_values(["release_time", "event_type", "title"])
            .drop_duplicates(["release_time", "title"], keep="last")
            .reset_index(drop=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data_cache/global_economic_calendar.zip")
    parser.add_argument("--output", default="data_cache/economic_surprises_2025.csv")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-10-01")
    args = parser.parse_args()
    raw = pd.read_csv(args.input, low_memory=False)
    out = import_calendar(raw, start=args.start, end=args.end)
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False, encoding="utf-8")
    print(f"saved rows={len(out)} events={out['release_time'].nunique()} to {target}")
    print(out.groupby("event_type").size().to_string())
    mismatch = int((out["source_time_delta_minutes"].abs() > 1).sum())
    print(f"source_time_mismatches_gt_1m={mismatch}")


if __name__ == "__main__":
    main()

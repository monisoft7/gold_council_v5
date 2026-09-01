# -*- coding: utf-8 -*-
"""يبني تقويم أحداث تاريخياً من تواريخ الإصدار الرسمية المخزنة.

FRED/ALFRED يوفر تاريخ الإصدار الأول. نشرات BLS تصدر 08:30 بتوقيت نيويورك؛
يُحوّل التوقيت إلى UTC مع DST بدلاً من تثبيت 12:30 طوال السنة.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


SERIES = {
    "fred_cpi.csv": ("US CPI official release", "CPI"),
    "fred_payrolls.csv": ("US Nonfarm Payrolls official release", "NFP"),
}
NEW_YORK = ZoneInfo("America/New_York")


def bls_release_time(day) -> pd.Timestamp:
    date = pd.Timestamp(day).date()
    return pd.Timestamp(year=date.year, month=date.month, day=date.day,
                        hour=8, minute=30, tz=NEW_YORK).tz_convert("UTC")


def build(official_dir: str, existing: str | None = None) -> pd.DataFrame:
    rows = []
    base = Path(official_dir)
    for filename, (title, section) in SERIES.items():
        frame = pd.read_csv(base / filename)
        dates = pd.to_datetime(frame["released_at"], errors="coerce", utc=True).dropna()
        for day in dates.dt.normalize().drop_duplicates():
            rows.append({"time": bls_release_time(day),
                         "title": title, "source": "FRED/ALFRED+BLS",
                         "section": section})
    if existing and Path(existing).exists():
        old = pd.read_csv(existing)
        old["time"] = pd.to_datetime(old["time"], errors="coerce", utc=True)
        rows.extend(old.dropna(subset=["time"])[["time", "title", "source", "section"]]
                    .to_dict("records"))
    out = pd.DataFrame(rows)
    out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=True)
    return (out.dropna(subset=["time"])
            .drop_duplicates(subset=["time", "section"], keep="last")
            .sort_values("time").reset_index(drop=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-dir", default="data_cache/official")
    parser.add_argument("--existing", default="data_cache/events_2008_2026.csv")
    parser.add_argument("--out", default="data_cache/events_2008_2026.csv")
    args = parser.parse_args()
    data = build(args.official_dir, args.existing)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(target, index=False, encoding="utf-8")
    print(f"saved {len(data)} events {data.time.min()} -> {data.time.max()} to {target}")


if __name__ == "__main__":
    main()

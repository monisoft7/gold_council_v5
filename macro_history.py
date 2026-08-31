# -*- coding: utf-8 -*-
"""بناء أرشيف يومي للأصول المؤثرة في الذهب مع أوقات توفر محافظة.

المصدر الافتراضي الحالي Yahoo chart لأنه مجاني ولا يحتاج مفتاحاً. الواجهة
مستقلة كي نستبدله لاحقاً بـ Treasury/FRED دون تغيير الوكلاء أو الباكتيست.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pandas as pd
import requests


SYMBOLS = {
    "dxy": "DX-Y.NYB",
    "us10y": "^TNX",
    "spx": "^GSPC",
    "vix": "^VIX",
}
UA = {"User-Agent": "GoldCouncil/1.0 point-in-time-research"}


def fetch_daily(symbol: str, start: str, end: str) -> pd.DataFrame:
    start_ts = int(pd.Timestamp(start, tz="UTC").timestamp())
    # Yahoo period2 حصري؛ نضيف يوماً لتضمين النهاية المطلوبة.
    end_ts = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = requests.get(url, params={
        "interval": "1d", "period1": start_ts, "period2": end_ts,
        "events": "history",
    }, headers=UA, timeout=30)
    response.raise_for_status()
    payload = response.json()["chart"]["result"][0]
    quote = payload["indicators"]["quote"][0]
    out = pd.DataFrame({
        "observed_at": pd.to_datetime(payload["timestamp"], unit="s", utc=True),
        "close": quote["close"],
    }).dropna(subset=["close"])
    return out.reset_index(drop=True)


def assemble(series: dict[str, pd.DataFrame], availability_lag="1D") -> pd.DataFrame:
    """يوحد السلاسل حسب جلسة UTC ويجعلها متاحة في اليوم التالي تحفظياً."""
    merged = None
    for name, frame in series.items():
        part = frame.copy()
        part["session"] = pd.to_datetime(part["observed_at"], utc=True).dt.floor("D")
        part = part[["session", "close"]].rename(columns={"close": name})
        merged = part if merged is None else merged.merge(part, on="session", how="outer")
    if merged is None:
        return pd.DataFrame(columns=["observed_at", "released_at", "available_at"])
    merged = merged.sort_values("session").reset_index(drop=True)
    merged["observed_at"] = merged.pop("session")
    merged["released_at"] = merged["observed_at"] + pd.Timedelta(availability_lag)
    merged["available_at"] = merged["released_at"]
    merged["source_id"] = "yahoo_chart_daily"
    return merged


def build(start: str, end: str) -> pd.DataFrame:
    return assemble({name: fetch_daily(symbol, start, end)
                     for name, symbol in SYMBOLS.items()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default="macro_history.csv")
    args = parser.parse_args()
    data = build(args.start, args.end)
    data.to_csv(args.out, index=False, encoding="utf-8")
    print(f"saved {len(data)} point-in-time rows -> {args.out}")


if __name__ == "__main__":
    main()

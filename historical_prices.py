# -*- coding: utf-8 -*-
"""أرشيف OHLC يومي للذهب مع فحوص جودة صريحة.

يستخدم Yahoo Chart كمصدر مجاني لعقد GC المستمر. هذا مناسب للبحث الاتجاهي،
لكن ليس بديلاً عن بيانات وسيط التنفيذ بسبب لف العقود واختلاف XAU spot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import requests


URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
UA = {"User-Agent": "GoldCouncil/1.0 historical-research"}


def fetch_ohlcv(symbol="GC=F", start="2008-01-01", end="2026-08-30",
                timeout=60) -> pd.DataFrame:
    start_ts = int(pd.Timestamp(start, tz="UTC").timestamp())
    end_ts = int((pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).timestamp())
    try:
        response = requests.get(URL.format(symbol=symbol), params={
            "period1": start_ts, "period2": end_ts, "interval": "1d",
            "events": "history", "includeAdjustedClose": "true",
        }, headers=UA, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else "network"
        raise RuntimeError(f"historical price download failed (status={status})") from None
    result = response.json()["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
    frame = pd.DataFrame({
        "time": pd.to_datetime(result["timestamp"], unit="s", utc=True),
        "open": quote["open"], "high": quote["high"], "low": quote["low"],
        "close": quote["close"], "volume": quote.get("volume"),
        "adjusted_close": adjusted if adjusted is not None else quote["close"],
    })
    return (frame.dropna(subset=["time", "open", "high", "low", "close"])
            .sort_values("time").drop_duplicates("time").reset_index(drop=True))


def audit(frame: pd.DataFrame) -> dict:
    x = frame.copy()
    x["time"] = pd.to_datetime(x["time"], utc=True, errors="coerce")
    invalid_ohlc = x["high"] < x["low"]
    settlement_outside = ((x["high"] < x[["open", "close"]].max(axis=1)) |
                          (x["low"] > x[["open", "close"]].min(axis=1)))
    returns = pd.to_numeric(x["close"], errors="coerce").pct_change()
    return {
        "rows": int(len(x)), "start": str(x["time"].min()),
        "end": str(x["time"].max()),
        "duplicates": int(x["time"].duplicated().sum()),
        "invalid_ohlc": int(invalid_ohlc.sum()),
        "settlement_outside_intraday_range": int(settlement_outside.sum()),
        "missing_close": int(x["close"].isna().sum()),
        "extreme_daily_moves_gt_10pct": int((returns.abs() > 0.10).sum()),
        "median_daily_move_pct": round(float(returns.abs().median() * 100), 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GC=F")
    parser.add_argument("--start", default="2008-01-01")
    parser.add_argument("--end", default="2026-08-30")
    parser.add_argument("--out", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--audit-out", default="data_cache/gold_daily_audit.json")
    args = parser.parse_args()
    frame = fetch_ohlcv(args.symbol, args.start, args.end)
    invalid_mask = frame["high"] < frame["low"]
    quarantined = frame.loc[invalid_mask].copy()
    frame = frame.loc[~invalid_mask].reset_index(drop=True)
    report = audit(frame)
    report["quarantined_rows"] = int(len(quarantined))
    if len(quarantined):
        quarantine_path = Path(args.out).with_name("gold_daily_quarantine.csv")
        quarantined.to_csv(quarantine_path, index=False, encoding="utf-8")
        report["quarantine_path"] = str(quarantine_path)
    if report["invalid_ohlc"] or report["duplicates"]:
        raise RuntimeError(f"price quality gate failed: {report}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out, index=False, encoding="utf-8")
    Path(args.audit_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

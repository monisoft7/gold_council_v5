# -*- coding: utf-8 -*-
"""Fetch continuous historical bars from the configured DEMO MT5 account."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from mt5_event_history import connection_from_env


def fetch_bars(bridge, *, start, end, timeframe="M15", chunk_days=60) -> pd.DataFrame:
    mt5 = bridge.mt5
    timeframe_code = getattr(mt5, f"TIMEFRAME_{timeframe}")
    cursor = pd.Timestamp(start)
    cursor = cursor.tz_localize("UTC") if cursor.tzinfo is None else cursor.tz_convert("UTC")
    finish = pd.Timestamp(end)
    finish = finish.tz_localize("UTC") if finish.tzinfo is None else finish.tz_convert("UTC")
    chunks = []
    while cursor < finish:
        chunk_end = min(finish, cursor + pd.Timedelta(days=int(chunk_days)))
        rates = mt5.copy_rates_range(
            bridge.symbol, timeframe_code, cursor.to_pydatetime(), chunk_end.to_pydatetime()
        )
        if rates is None:
            raise RuntimeError(f"MT5 copy_rates_range failed at {cursor}: {mt5.last_error()}")
        if len(rates):
            chunks.append(pd.DataFrame(rates))
        cursor = chunk_end
    if not chunks:
        return pd.DataFrame()
    frame = pd.concat(chunks, ignore_index=True)
    frame["time"] = pd.to_datetime(frame["time"], unit="s", errors="coerce", utc=True)
    frame = frame.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")
    if "volume" not in frame:
        frame["volume"] = frame.get("real_volume", frame.get("tick_volume", 0))
    return frame.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--timeframe", choices=("M5", "M15", "H1", "D1"), default="M15")
    parser.add_argument("--chunk-days", type=int, default=60)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    bridge = connection_from_env()
    try:
        account = bridge.connect()
        frame = fetch_bars(
            bridge, start=args.start, end=args.end,
            timeframe=args.timeframe, chunk_days=args.chunk_days,
        )
        if frame.empty:
            raise RuntimeError("MT5 returned no historical bars")
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        frame.to_csv(temporary, index=False, encoding="utf-8")
        temporary.replace(target)
        print({
            "status": "ok", "demo": account["demo"], "symbol": account["symbol"],
            "timeframe": args.timeframe, "rows": len(frame),
            "start": frame["time"].min().isoformat(),
            "end": frame["time"].max().isoformat(), "output": str(target),
        })
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()

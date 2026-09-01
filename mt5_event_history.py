# -*- coding: utf-8 -*-
"""قراءة شموع MT5 حول الأحداث الاقتصادية، بلا أي مسار لإرسال أوامر."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from env_loader import env
from mt5_demo_bridge import MT5ConnectionConfig, MT5DemoBridge


NEW_YORK = ZoneInfo("America/New_York")
TIMEFRAME_MINUTES = {"M5": 5, "M15": 15, "H1": 60}


def normalize_event_type(section: str, title: str) -> str | None:
    text = f" {section} {title} ".casefold()
    if "fomc" in text or "federal reserve" in text or "فائدة" in text:
        return "FOMC"
    if "nonfarm" in text or "non-farm" in text or "payroll" in text or "وظائف" in text:
        return "NFP"
    if " cpi" in text or "consumer price" in text or "تضخم" in text:
        return "CPI"
    return None


def canonical_release_time(day, event_type: str) -> pd.Timestamp:
    """Use official US release conventions and DST-aware conversion."""
    date = pd.Timestamp(day).date()
    hour, minute = (14, 0) if event_type == "FOMC" else (8, 30)
    local = pd.Timestamp(year=date.year, month=date.month, day=date.day,
                         hour=hour, minute=minute, tz=NEW_YORK)
    return local.tz_convert("UTC")


def canonicalize_events(events: pd.DataFrame, *, start=None, end=None) -> pd.DataFrame:
    frame = events.copy()
    frame["original_time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    frame["event_type"] = [
        normalize_event_type(str(section), str(title))
        for section, title in zip(frame.get("section", ""), frame.get("title", ""))
    ]
    frame = frame.dropna(subset=["original_time", "event_type"]).copy()
    frame["event_time"] = [
        canonical_release_time(time, kind)
        for time, kind in zip(frame["original_time"], frame["event_type"])
    ]
    if start is not None:
        frame = frame[frame["event_time"] >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        frame = frame[frame["event_time"] < pd.Timestamp(end, tz="UTC")]
    return (frame.sort_values(["event_time", "event_type"])
            .drop_duplicates(["event_time", "event_type"], keep="last")
            .reset_index(drop=True))


def load_event_schedule(events: pd.DataFrame, *, start=None, end=None) -> pd.DataFrame:
    """Accept either the official schedule or imported surprise-event schema."""
    if {"release_time", "event_type"}.issubset(events.columns):
        frame = events.copy()
        frame["event_time"] = pd.to_datetime(frame["release_time"], errors="coerce", utc=True)
        frame = frame.dropna(subset=["event_time", "event_type"])
        if start is not None:
            frame = frame[frame["event_time"] >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            frame = frame[frame["event_time"] < pd.Timestamp(end, tz="UTC")]
        return (frame.sort_values(["event_time", "event_type"])
                .drop_duplicates(["event_time", "event_type"], keep="last")
                .reset_index(drop=True))
    return canonicalize_events(events, start=start, end=end)


def extract_event_window(rates, event_time, timeframe_minutes: int,
                         bars_before: int = 24, bars_after: int = 72) -> pd.DataFrame:
    """Split at the first bar opening at/after release; never use a partial pre-bar."""
    frame = pd.DataFrame(rates).copy()
    if frame.empty or "time" not in frame:
        return pd.DataFrame()
    frame["time"] = pd.to_datetime(frame["time"], unit="s", errors="coerce", utc=True)
    frame = frame.dropna(subset=["time"]).sort_values("time").drop_duplicates("time")
    event = pd.Timestamp(event_time)
    event = event.tz_localize("UTC") if event.tzinfo is None else event.tz_convert("UTC")
    entry_time = event.ceil(f"{int(timeframe_minutes)}min")
    before = frame[frame["time"] < entry_time].tail(int(bars_before)).copy()
    after = frame[frame["time"] >= entry_time].head(int(bars_after)).copy()
    before["phase"] = "before"
    after["phase"] = "after"
    out = pd.concat([before, after], ignore_index=True)
    if out.empty:
        return out
    out["event_time"] = event
    out["entry_time"] = entry_time
    out["minutes_from_event"] = (out["time"] - event).dt.total_seconds() / 60
    return out


def event_return_summary(window: pd.DataFrame, *, timeframe_minutes: int,
                         point: float = 0.01,
                         horizons_minutes=(15, 60, 240, 1440)) -> dict:
    """Return post-release moves, with one observed spread charged per round trip."""
    if window is None or window.empty or "phase" not in window:
        return {"status": "no_post_release_bars"}
    post = window[window["phase"] == "after"].copy()
    if post.empty:
        return {"status": "no_post_release_bars"}
    post["bar_end"] = post["time"] + pd.Timedelta(minutes=timeframe_minutes)
    entry = float(post.iloc[0]["open"])
    spread_points = float(post.iloc[0].get("spread", 0) or 0)
    spread_cost_pct = spread_points * float(point) / entry * 100 if entry else 0.0
    event_time = pd.Timestamp(post.iloc[0]["event_time"])
    result = {
        "status": "ok", "entry_time": post.iloc[0]["time"], "entry_price": entry,
        "spread_points": spread_points, "spread_cost_pct": spread_cost_pct,
    }
    for horizon in horizons_minutes:
        eligible = post[post["bar_end"] >= event_time + pd.Timedelta(minutes=horizon)]
        key = f"return_{int(horizon)}m_pct"
        if eligible.empty or not entry:
            result[key] = None
        else:
            raw = (float(eligible.iloc[0]["close"]) / entry - 1.0) * 100
            result[key] = raw - spread_cost_pct
    return result


class MT5EventHistoryReader:
    """Strict-demo market-data reader. This class has no order method."""

    def __init__(self, bridge: MT5DemoBridge):
        self.bridge = bridge

    def fetch(self, event_time, *, timeframe="M5", bars_before=24,
              bars_after=300) -> pd.DataFrame:
        minutes = TIMEFRAME_MINUTES[timeframe]
        mt5 = self.bridge.mt5
        tf_code = getattr(mt5, f"TIMEFRAME_{timeframe}")
        event = pd.Timestamp(event_time)
        event = event.tz_localize("UTC") if event.tzinfo is None else event.tz_convert("UTC")
        start = event - pd.Timedelta(minutes=minutes * (bars_before + 3))
        end = event + pd.Timedelta(minutes=minutes * (bars_after + 3))
        rates = mt5.copy_rates_range(
            self.bridge.symbol, tf_code, start.to_pydatetime(), end.to_pydatetime()
        )
        return extract_event_window(rates, event, minutes, bars_before, bars_after)


def connection_from_env() -> MT5DemoBridge:
    login = env.get("MT5_LOGIN")
    return MT5DemoBridge(MT5ConnectionConfig(
        terminal_path=env.get("MT5_TERMINAL_PATH"),
        login=int(login) if login else None,
        password=env.get("MT5_PASSWORD"),
        server=env.get("MT5_SERVER"),
        symbol=env.get("MT5_SYMBOL", "XAUUSD"),
    ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", default="data_cache/events_2008_2026.csv")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-09-01")
    parser.add_argument("--timeframe", choices=tuple(TIMEFRAME_MINUTES), default="M5")
    parser.add_argument("--bars-before", type=int, default=24)
    parser.add_argument("--bars-after", type=int, default=300)
    parser.add_argument("--output", default="data_cache/mt5_event_bars.csv")
    parser.add_argument("--audit-output", default="data_cache/mt5_event_bars_audit.json")
    args = parser.parse_args()

    events = load_event_schedule(pd.read_csv(args.events), start=args.start, end=args.end)
    bridge = connection_from_env()
    info = bridge.connect()
    reader = MT5EventHistoryReader(bridge)
    chunks = []
    try:
        point = float(getattr(bridge.mt5.symbol_info(bridge.symbol), "point", 0.01) or 0.01)
        summaries = []
        for event in events.itertuples():
            window = reader.fetch(event.event_time, timeframe=args.timeframe,
                                  bars_before=args.bars_before, bars_after=args.bars_after)
            if not window.empty:
                window["event_type"] = event.event_type
                chunks.append(window)
            summary = event_return_summary(
                window, timeframe_minutes=TIMEFRAME_MINUTES[args.timeframe], point=point
            )
            summaries.append({"event_time": event.event_time.isoformat(),
                              "event_type": event.event_type, **summary})
    finally:
        bridge.shutdown()

    output = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(target, index=False, encoding="utf-8")
    report = {
        "demo": True, "server": info["server"], "symbol": info["symbol"],
        "timeframe": args.timeframe, "requested_events": len(events),
        "events_with_bars": int(output["event_time"].nunique()) if not output.empty else 0,
        "rows": len(output), "summaries": summaries,
    }
    Path(args.audit_output).write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                  default=str), encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key != "summaries"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

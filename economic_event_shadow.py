# -*- coding: utf-8 -*-
"""مراقبة NFP لعام 2026 في Shadow فقط، دون بناء أو إرسال أي أمر MT5."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from economic_event_strategy import EventStrategyConfig, pre_event_atr, simulate_event
from mt5_event_history import MT5EventHistoryReader, connection_from_env


DEFAULT_SNAPSHOTS = Path("data_cache/economic_calendar_snapshots.csv")
DEFAULT_JOURNAL = Path("data_cache/economic_event_shadow.jsonl")
SHADOW_CONFIG = EventStrategyConfig(sl_atr_mult=3.0, allowed_event_types=("NFP",))


def _is_main_nfp(title: str) -> bool:
    text = title.casefold()
    return "nonfarm payrolls" in text or "non-farm employment change" in text


def completed_nfp_signals(history: pd.DataFrame, *, as_of=None) -> pd.DataFrame:
    """Return only NFP actuals observed by the collector no later than ``as_of``."""
    now = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    frame = history.copy()
    frame["release_time"] = pd.to_datetime(frame["release_time"], errors="coerce", utc=True)
    frame["actual_available_at"] = pd.to_datetime(
        frame["actual_available_at"], errors="coerce", utc=True
    )
    frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], errors="coerce", utc=True)
    frame["gold_score"] = pd.to_numeric(frame.get("gold_score"), errors="coerce")
    frame = frame[
        frame["title"].astype(str).map(_is_main_nfp)
        & frame["actual_available_at"].notna()
        & (frame["actual_available_at"] <= now)
        & frame["gold_score"].notna()
    ].copy()
    frame = (frame.sort_values("fetched_at")
             .drop_duplicates(["release_time", "title"], keep="last"))
    frame["event_type"] = "NFP"
    frame["signal"] = frame["gold_score"].apply(
        lambda value: 1 if value > SHADOW_CONFIG.min_abs_score
        else -1 if value < -SHADOW_CONFIG.min_abs_score else 0
    )
    return frame[frame["signal"] != 0].sort_values("actual_available_at").reset_index(drop=True)


def read_journal(path: str | Path = DEFAULT_JOURNAL) -> list[dict]:
    target = Path(path)
    if not target.exists():
        return []
    rows = []
    for line in target.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_journal(record: dict, path: str | Path = DEFAULT_JOURNAL) -> None:
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        handle.flush()


def latest_states(rows: list[dict]) -> dict[str, dict]:
    states = {}
    for row in rows:
        event_id = row.get("event_id")
        if event_id:
            states[event_id] = row
    return states


def _event_id(release_time) -> str:
    return f"NFP:{pd.Timestamp(release_time).isoformat()}"


def run_shadow_once(*, snapshots=DEFAULT_SNAPSHOTS, journal=DEFAULT_JOURNAL,
                    now=None, max_new_signal_age_minutes=5) -> dict:
    """Advance pending/open shadow states. This function never calls an order API."""
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    snapshot_path = Path(snapshots)
    if not snapshot_path.exists():
        return {"status": "skipped", "reason": "no_calendar_snapshots", "actions": []}
    signals = completed_nfp_signals(pd.read_csv(snapshot_path), as_of=current)
    states = latest_states(read_journal(journal))
    actions = []
    # لا نسجل إشارة قديمة بأثر رجعي؛ يجب أن يكون المجمع قد رآها الآن فعلياً.
    for row in signals.itertuples():
        event_id = _event_id(row.release_time)
        if event_id in states:
            continue
        age = (current - pd.Timestamp(row.actual_available_at)).total_seconds() / 60
        if 0 <= age <= max_new_signal_age_minutes:
            record = {
                "recorded_at": current.isoformat(), "event_id": event_id,
                "status": "pending", "release_time": row.release_time,
                "actual_available_at": row.actual_available_at,
                "signal": int(row.signal), "gold_score": float(row.gold_score),
                "actual": row.actual, "forecast": row.forecast,
                "strategy": "nfp_surprise_m15_4h_shadow_v1",
            }
            append_journal(record, journal); states[event_id] = record
            actions.append({"event_id": event_id, "status": "pending"})

    active = [row for row in states.values() if row.get("status") in {"pending", "open"}]
    if not active:
        return {"status": "ok", "reason": "no_active_nfp_signal", "actions": actions}

    bridge = connection_from_env()
    try:
        account = bridge.connect()
        info = bridge.mt5.symbol_info(bridge.symbol)
        point = float(getattr(info, "point", SHADOW_CONFIG.point) or SHADOW_CONFIG.point)
        config = EventStrategyConfig(**{**SHADOW_CONFIG.__dict__, "point": point})
        reader = MT5EventHistoryReader(bridge)
        for state in active:
            event_id = state["event_id"]
            decision_time = pd.Timestamp(state["actual_available_at"])
            window = reader.fetch(decision_time, timeframe="M15", bars_before=16, bars_after=24)
            if window.empty:
                continue
            post = window[window["phase"] == "after"].sort_values("time")
            if state["status"] == "pending" and not post.empty:
                atr = pre_event_atr(window, config.atr_period)
                if atr is None:
                    continue
                entry_bar = post.iloc[0]
                entry_time = pd.Timestamp(entry_bar["time"])
                if entry_time > current:
                    continue
                entry = float(entry_bar["open"])
                stop = entry - int(state["signal"]) * config.sl_atr_mult * atr
                record = {
                    **state, "recorded_at": current.isoformat(), "status": "open",
                    "entry_time": entry_time, "entry_price": entry, "atr": atr,
                    "stop_price": stop, "risk_pct": config.risk_pct,
                    "account_suffix": account["account_suffix"], "demo": True,
                    "execution": False,
                }
                append_journal(record, journal); states[event_id] = record; state = record
                actions.append({"event_id": event_id, "status": "open"})
            if state["status"] != "open":
                continue
            due = pd.Timestamp(state["entry_time"]) + pd.Timedelta(minutes=config.holding_minutes)
            if current < due:
                continue
            signal = SimpleNamespace(
                signal=int(state["signal"]), event_time=decision_time,
                event_type="NFP", gold_score=float(state["gold_score"]),
                component_count=1, component_conflict=False,
            )
            trade = simulate_event(window, signal, config)
            if trade is None:
                continue
            record = {
                **state, **trade, "recorded_at": current.isoformat(), "status": "closed",
                "execution": False, "demo": True,
            }
            append_journal(record, journal); states[event_id] = record
            actions.append({"event_id": event_id, "status": "closed",
                            "net_return_pct": trade["net_return_pct"]})
    finally:
        bridge.shutdown()
    return {"status": "ok", "actions": actions, "active_before": len(active)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshots", default=str(DEFAULT_SNAPSHOTS))
    parser.add_argument("--journal", default=str(DEFAULT_JOURNAL))
    args = parser.parse_args()
    print(json.dumps(run_shadow_once(snapshots=args.snapshots, journal=args.journal),
                     ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

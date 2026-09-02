# -*- coding: utf-8 -*-
"""تشغيل مجلس الذهب على بيانات MT5 وإرسال الأوامر إلى حساب DEMO فقط."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

import data_feeds
import decision_pipeline
from env_loader import env
from mt5_demo_bridge import MT5ConnectionConfig, MT5DemoBridge
import paper_journal


EXECUTION_JOURNAL = Path(__file__).resolve().parent / "data_cache" / "mt5_demo_execution.jsonl"
EXECUTION_HOUR_UTC = 18
EXECUTION_WINDOW_MINUTES = 30
LOOP_ERROR_RETRY_SECONDS = 300


def _config() -> MT5ConnectionConfig:
    login_text = env.get("MT5_LOGIN")
    return MT5ConnectionConfig(
        terminal_path=env.get("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        login=int(login_text) if login_text else None,
        password=env.get("MT5_PASSWORD"),
        server=env.get("MT5_SERVER"),
        symbol=env.get("MT5_SYMBOL", "XAUUSD"),
        deviation=int(env.get("MT5_DEVIATION", "20")),
    )


def _append_execution(payload: dict) -> None:
    EXECUTION_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with EXECUTION_JOURNAL.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def within_execution_window(now=None, *, hour_utc=EXECUTION_HOUR_UTC,
                            tolerance_minutes=EXECUTION_WINDOW_MINUTES) -> bool:
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime):
        current = datetime.fromisoformat(str(current).replace("Z", "+00:00"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    target = current.replace(hour=int(hour_utc), minute=0, second=0, microsecond=0)
    return abs((current - target).total_seconds()) <= int(tolerance_minutes) * 60


def seconds_until_execution_window(now=None, *, hour_utc=EXECUTION_HOUR_UTC,
                                   tolerance_minutes=EXECUTION_WINDOW_MINUTES) -> int:
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime):
        current = datetime.fromisoformat(str(current).replace("Z", "+00:00"))
    current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None \
        else current.astimezone(timezone.utc)
    centre = current.replace(hour=int(hour_utc), minute=0, second=0, microsecond=0)
    window_start = centre - timedelta(minutes=int(tolerance_minutes))
    window_end = centre + timedelta(minutes=int(tolerance_minutes))
    if current < window_start:
        target = window_start
    elif current <= window_end:
        return 0
    else:
        target = window_start + timedelta(days=1)
    return max(0, int((target - current).total_seconds()))


def run_once(*, execute_demo: bool = False, now=None) -> dict:
    decision_time = now or datetime.now(timezone.utc)
    if decision_time.tzinfo is None:
        decision_time = decision_time.replace(tzinfo=timezone.utc)
    else:
        decision_time = decision_time.astimezone(timezone.utc)
    bridge = MT5DemoBridge(_config())
    try:
        account = bridge.connect()
        maintenance = bridge.close_expired_positions(
            now=decision_time, max_age_minutes=240, execute=execute_demo
        )
        in_window = within_execution_window(decision_time)
        if execute_demo and not in_window:
            payload = {
                "recorded_at": decision_time.isoformat(), "paper_run_id": None,
                "account": account, "execute_demo": True, "risk_pct": 0.25,
                "strategy_profile": "intraday_4h",
                "execution_window": {
                    "hour_utc": EXECUTION_HOUR_UTC,
                    "tolerance_minutes": EXECUTION_WINDOW_MINUTES,
                    "inside_now": False,
                },
                "position_maintenance": maintenance,
                "decision": None,
                "execution": {"status": "skipped", "reason": "خارج نافذة قرار 18:00 UTC"},
            }
            _append_execution(payload)
            return payload
        daily = bridge.closed_daily_bars()
        ask = bridge.current_ask()
        news = data_feeds.get_news(per_feed=8)
        # الأداء التاريخي الحالي غير مثبت؛ سقف الديمو 0.25% حتى يتحسن
        # عامل الربح خارج العينة. لا يمكن لمتغير البيئة تجاوز هذا السقف.
        risk_pct = min(0.25, max(0.01, float(env.get("RISK_PCT", "0.25"))))
        result = decision_pipeline.run_decision(
            daily, news,
            spot_price=ask,
            capital=account["equity"],
            risk_pct=risk_pct,
            as_of=decision_time,
            load_cached_macro=True,
            load_cached_surprises=True,
            strategy_profile="intraday_4h",
        )
        result["news"] = news
        record = paper_journal.append_record(result)
        if execute_demo and not in_window:
            execution = {
                "status": "skipped",
                "reason": "خارج نافذة التنفيذ المختبرة 18:00 UTC ±30 دقيقة",
            }
        else:
            execution = bridge.submit_decision(result["dec"], execute=execute_demo)
        payload = {
            "recorded_at": decision_time.isoformat(),
            "paper_run_id": record["run_id"],
            "account": account,
            "execute_demo": execute_demo,
            "risk_pct": risk_pct,
            "strategy_profile": "intraday_4h",
            "execution_window": {
                "hour_utc": EXECUTION_HOUR_UTC,
                "tolerance_minutes": EXECUTION_WINDOW_MINUTES,
                "inside_now": in_window,
            },
            "position_maintenance": maintenance,
            "decision": {
                "signal": result["dec"]["signal"],
                "label": result["dec"]["decision"],
                "score": result["dec"]["final_score"],
                "position_oz": result["dec"]["position_oz"],
            },
            "execution": execution,
        }
        _append_execution(payload)
        return payload
    finally:
        bridge.shutdown()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-demo", action="store_true",
                        help="يرسل إلى حساب DEMO بعد order_check؛ بدونه Dry Run")
    parser.add_argument("--loop", action="store_true",
                        help="تشغيل مستمر؛ يفضل مرة يومياً بعد إغلاق شمعة الذهب")
    parser.add_argument("--interval-min", type=int, default=1440)
    args = parser.parse_args()
    while True:
        try:
            payload = run_once(execute_demo=args.execute_demo)
        except Exception as exc:
            # تشغيل الحلقة يجب أن يتعافى من انقطاع MT5 أو الشبكة بدلاً من
            # سقوط الحارس بالكامل. التشغيل لمرة واحدة يبقى صارماً للتشخيص.
            if not args.loop:
                raise
            payload = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "status": "service_error",
                "error_type": type(exc).__name__,
                "reason": str(exc),
                "retry_seconds": LOOP_ERROR_RETRY_SECONDS,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
            time.sleep(LOOP_ERROR_RETRY_SECONDS)
            continue
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        if not args.loop:
            break
        wait_seconds = max(300, args.interval_min * 60)
        maintenance = payload.get("position_maintenance") or {}
        if args.execute_demo \
                and not payload.get("execution_window", {}).get("inside_now", False) \
                and int(maintenance.get("managed_position_count", 0)) == 0:
            wait_seconds = max(
                wait_seconds,
                seconds_until_execution_window(payload.get("recorded_at")),
            )
        time.sleep(wait_seconds)


if __name__ == "__main__":
    main()

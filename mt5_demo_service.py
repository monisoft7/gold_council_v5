# -*- coding: utf-8 -*-
"""تشغيل مجلس الذهب على بيانات MT5 وإرسال الأوامر إلى حساب DEMO فقط."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import data_feeds
import decision_pipeline
from env_loader import env
from mt5_demo_bridge import MT5ConnectionConfig, MT5DemoBridge
import paper_journal


EXECUTION_JOURNAL = Path(__file__).resolve().parent / "data_cache" / "mt5_demo_execution.jsonl"


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


def run_once(*, execute_demo: bool = False) -> dict:
    bridge = MT5DemoBridge(_config())
    try:
        account = bridge.connect()
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
            as_of=datetime.now(timezone.utc),
            load_cached_macro=True,
        )
        result["news"] = news
        record = paper_journal.append_record(result)
        execution = bridge.submit_decision(result["dec"], execute=execute_demo)
        payload = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "paper_run_id": record["run_id"],
            "account": account,
            "execute_demo": execute_demo,
            "risk_pct": risk_pct,
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-demo", action="store_true",
                        help="يرسل إلى حساب DEMO بعد order_check؛ بدونه Dry Run")
    parser.add_argument("--loop", action="store_true",
                        help="تشغيل مستمر؛ يفضل مرة يومياً بعد إغلاق شمعة الذهب")
    parser.add_argument("--interval-min", type=int, default=1440)
    args = parser.parse_args()
    while True:
        payload = run_once(execute_demo=args.execute_demo)
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        if not args.loop:
            break
        time.sleep(max(300, args.interval_min * 60))


if __name__ == "__main__":
    main()

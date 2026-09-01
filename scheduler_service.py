# -*- coding: utf-8 -*-
"""خدمة الجدولة — الفجوة 7 (التشغيل 24/7 بدون CMD مفتوح).

تعقد اجتماع المجلس كل N دقيقة، وترسل التوصية إلى تيليجرام عند صدورها أو تغيّرها.
تعمل بـ APScheduler إن وُجد، وإلا بحلقة sleep بسيطة.

تشغيل:
  python scheduler_service.py            # كل 30 دقيقة (افتراضي)
  INTERVAL_MIN=15 python scheduler_service.py

المفاتيح تُقرأ من .env عبر env_loader (TG_TOKEN/TG_CHAT_ID).
"""
import os
import sys
import time
import traceback

from env_loader import env
import data_feeds
import decision_pipeline
from build_economic_calendar import update_snapshot as update_economic_calendar
from economic_event_shadow import run_shadow_once
import paper_journal
import telegram_notifier as tg


def run_meeting() -> dict:
    """اجتماع واحد كامل — يعيد القرار والسعر."""
    spot, daily, intra, news = data_feeds.collect_all()
    calendar_warning = None
    try:
        update_economic_calendar(high_impact_only=True)
        decision_pipeline.clear_data_caches()
    except Exception as exc:
        calendar_warning = f"economic calendar refresh failed: {exc}"
    result = decision_pipeline.run_decision(
        daily, news, spot_price=spot.get("price"),
        capital=float(os.environ.get("PAPER_CAPITAL", "10000")),
        risk_pct=float(os.environ.get("RISK_PCT", "1.0")),
        load_cached_macro=True,
        load_cached_surprises=True,
    )
    result["news"] = news
    result["intraday"] = intra
    try:
        result["event_shadow"] = run_shadow_once()
    except Exception as exc:
        result["event_shadow"] = {"status": "error", "reason": str(exc)}
        result["dec"].setdefault("pipeline_warnings", []).append(
            f"economic event shadow failed: {exc}"
        )
    if calendar_warning:
        result["dec"].setdefault("pipeline_warnings", []).append(calendar_warning)
    return result


def notify(result: dict, token: str, chat_id: str, prev_decision: str,
           notify_mode: str = "change"):
    dec = result["dec"]
    if notify_mode == "change" and dec["decision"] == prev_decision:
        return prev_decision, False
    titles = [n["title"] for n in result["news"][:4]]
    ok, msg = tg.send_telegram(token, chat_id,
                               tg.build_signal_message(dec, result["last_price"],
                                                       result["reports"], titles,
                                                       result.get("event_shadow")))
    print(f"[TG] {'✅' if ok else '⚠'} {msg}")
    return dec["decision"], ok


def main():
    interval = int(os.environ.get("INTERVAL_MIN", "30"))
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    notify_mode = os.environ.get("TG_NOTIFY_MODE", "change").strip().lower()
    if not token or not chat_id:
        print("⚠ TG_TOKEN/TG_CHAT_ID غير موجودة في .env — الإشعارات معطلة، "
              "لكن الاجتماعات ستستمر وتُطبع هنا")
    print(f"🏆 خدمة مجلس الذهب — اجتماع كل {interval} دقيقة. Ctrl+C للإيقاف.")

    prev = None
    while True:
        try:
            print(f"\n=== اجتماع {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
            result = run_meeting()
            dec = result["dec"]
            record = paper_journal.append_record(result)
            print(f"القرار: {dec['decision']} | درجة {dec.get('final_score', 0):.1f} "
                  f"| ثقة {dec.get('confidence', 0):.0f}% | سعر {result['last_price']:.2f} "
                  f"| سجل {record['run_id']}")
            if token and chat_id:
                prev, _ = notify(result, token, chat_id, prev, notify_mode)
        except KeyboardInterrupt:
            print("\nإيقاف الخدمة.")
            break
        except Exception:
            traceback.print_exc()
        time.sleep(max(60, interval * 60))


if __name__ == "__main__":
    main()

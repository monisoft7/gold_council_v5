# -*- coding: utf-8 -*-
"""
وكيل الإشعارات اللحظية عبر تيليجرام.
يرسل التوصية النهائية فور صدورها (أو عند تغيّرها) إلى بوتك الخاص.

كيف تحصل على المفتاحين:
  1) TELEGRAM_BOT_TOKEN: افتح تيليجرام ← ابحث عن @BotFather ← أرسل /newbot
     ← اختر اسماً للبوت ← سيعطيك التوكن فوراً.
  2) TELEGRAM_CHAT_ID: افتح محادثة مع بوتك الجديد وأرسل له أي رسالة،
     ثم افتح @userinfobot وسيعطيك رقم الـ ID الخاص بك.
"""
import requests
import council


def send_telegram(token: str, chat_id: str, text: str, timeout=15):
    """يرسل رسالة HTML إلى تيليجرام. يعيد (نجاح؟, وصف النتيجة)."""
    if not token or not chat_id:
        return False, "التوكن أو Chat ID غير موجود — أدخلهما في الشريط الجانبي أو ملف .env"
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=timeout)
        if r.ok:
            return True, "تم الإرسال ✅"
        return False, f"رفض تيليجرام: {r.json().get('description', r.status_code)}"
    except Exception as e:
        return False, f"خطأ اتصال: {e}"


def build_signal_message(decision: dict, last_price: float,
                         reports: list, top_headlines: list,
                         shadow: dict | None = None) -> str:
    """يبني نص رسالة التوصية بصيغة HTML مرتبة."""
    lv = decision["levels"]
    lines = [
        "🏆 <b>مجلس الذهب — توصية لحظية</b>",
        "━━━━━━━━━━━━━━━",
        f"🥇 السعر الفوري: <b>{last_price:,.1f}$</b>",
        f"📣 القرار: <b>{decision['decision']}</b>",
        f"📊 درجة المجلس: {decision['final_score']:+.0f}/100 | "
        f"🎯 الثقة: {decision['confidence']:.0f}% | "
        f"🤝 الاتفاق: {decision['agreement']:.0f}%",
    ]
    if decision.get("research_only"):
        lines.append("🧪 <b>وضع بحثي غير معتمد للتداول الحقيقي</b>")
    if decision.get("risk_multiplier", 1.0) < 1.0:
        lines.append(f"🛡️ معامل المخاطرة: {decision['risk_multiplier']:.0%}")
    if decision.get("position_oz", 0) > 0:
        lines.append(
            f"📐 الحجم: <b>{decision['position_oz']:.4f} أونصة</b> | "
            f"التعرض {decision.get('exposure_pct', 0):.0f}% | "
            f"ميزانية الخطر {decision.get('risk_budget_usd', 0):,.2f}$"
        )
    if lv.get("entry"):
        lines += [
            "━━━━━━━━━━━━━━━",
            f"💵 الدخول: <b>{lv['entry']:,.1f}$</b>  ({lv['direction']})",
            f"🛑 وقف الخسارة: <b>{lv['sl']:,.1f}$</b>",
            f"🎯 الهدف 1: {lv['tp1']:,.1f}$   🎯 الهدف 2: {lv['tp2']:,.1f}$",
            f"⚖️ العائد/المخاطرة: {lv['rr']}",
        ]
    else:
        if decision.get("vetoed"):
            lines.append(f"⚪ الانتظار بسبب بوابة/فيتو: {decision['vetoed']}")
        else:
            lines.append("⚪ الإشارة لم تجتز شروط الجودة والتنفيذ؛ الانتظار هو القرار.")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("🗳️ <b>تصويت الوكلاء:</b>")
    voting = [r for r in reports if council.WEIGHTS_V2.get(r.key, 0) > 0]
    for r in voting:
        lines.append(f"{r.icon} {r.name}: {r.verdict} ({r.score:+.0f})")
    gates = [r for r in reports if r.key in {"risk", "event", "systematic_gate"}]
    if gates:
        lines.append("🛡️ <b>بوابات الأمان غير المصوّتة:</b>")
        for r in gates:
            lines.append(f"{r.icon} {r.name}: {r.verdict} — {r.summary}")
    experimental = [
        r for r in reports
        if r.flags.get("experimental") or r.flags.get("non_voting")
    ]
    if experimental:
        lines.append("🧪 <b>مراقبة تجريبية — لا تدخل الدرجة:</b>")
        for r in experimental:
            lines.append(f"{r.icon} {r.name}: {r.verdict} ({r.score:+.0f})")
    if shadow is not None:
        actions = shadow.get("actions") or []
        if actions:
            action_text = "، ".join(str(item.get("status")) for item in actions)
            lines.append(f"👤 NFP Shadow: {action_text} — بدون تنفيذ")
        else:
            lines.append("👤 NFP Shadow: لا توجد إشارة نشطة — بدون تنفيذ")
    if top_headlines:
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("🔥 <b>أهم الأخبار المحركة الآن:</b>")
        for h in top_headlines[:4]:
            lines.append(f"• {h}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("⚠️ تحليل تعليمي وليس نصيحة مالية.")
    return "\n".join(lines)

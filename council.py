# -*- coding: utf-8 -*-
"""رئيس المجلس V2 — مع فلتر الاتجاه وفيتو الانقسام لمنع الصفقات المعاكسة للاتجاه.
يدعم وضعين:
  1) المحرك القاعدي (افتراضي)
  2) وضع LLM: نموذج لغوي يقود الاجتماع (OpenAI/DeepSeek/Kimi/Qwen/Groq)"""
import config

THRESHOLDS = [
    (35,  "شراء قوي 🟢🟢", "#00c853"),
    (15,  "شراء 🟢", "#69fae0" if False else "#34d399"),
    (-15, "انتظار / محايد ⚪", "#9e9e9e"),
    (-35, "بيع 🔴", "#ef4444"),
    (-101, "بيع قوي 🔴🔴", "#b91c1c"),
]

# أوزان المجلس V2 — مضبوطة بعد باك-تست
WEIGHTS_V2 = {
    "macro": 0.18,
    "macro_data": 0.25,
    "tech": 0.30,
    "event": 0.00,              # خطر توقيت، لا اتجاه سعر
    "cross": 0.10,
    "season": 0.05,
    "pattern": 0.07,
    # المخاطر بوابة أمان وليست مصدراً لاتجاه السعر، لذلك لا تصوّت.
    "risk": 0.00,
    "expert": 0.10,
    "cot": 0.12,
}

EVIDENCE_FAMILY = {
    "tech": "price", "pattern": "price",
    "macro_data": "macro", "cross": "macro",
    "macro": "news", "expert": "news",
    "cot": "flows", "season": "seasonality",
}

# لا ترفع هذه العلامة قبل نجاح اختبار walk-forward مستقل بعينة كافية.
STRATEGY_VALIDATED = False


def _get_w(key):
    return WEIGHTS_V2.get(key, 0.10)


def chairman_decision(reports, tech_levels, atr_value, last_price,
                      trend_bias: float = 0.0, ema200: float = 0.0):
    """trend_bias: +1 = فوق EMA200 صاعد، -1 = تحت EMA200 هابط، 0 = غير معروف.
    فلتر الاتجاه: يُلغي القرارات القوية المعاكسة للاتجاه العام."""
    voting = []
    # المجلس هو المصدر الوحيد للأوزان. تجاهل الأوزان القديمة المزروعة داخل
    # الوكلاء، واستبعد وكلاء جمع البيانات/المخاطر من التصويت الاتجاهي.
    for r in reports:
        w = _get_w(r.key) if r.key in WEIGHTS_V2 else 0.0
        if w > 0:
            voting.append((r, w))
    wsum = sum(w for _, w in voting) or 1
    active = [(r, w) for r, w in voting if abs(r.score) > 10]
    active_wsum = sum(w for _, w in active)
    # المحايد لا يخفف الدليل الموجود. لكن قلة التغطية تخفض الدرجة بمعامل
    # ناعم، بينما شرط العائلات المستقلة أدناه يمنع قرار وكيل واحد.
    if active_wsum:
        active_score = sum(r.score * w for r, w in active) / active_wsum
        coverage = active_wsum / wsum
        final = active_score * max(0.65, coverage ** 0.5)
    else:
        final, coverage = 0.0, 0.0

    signs = [1 if r.score > 10 else -1 for r, _ in active]
    dominant = max(signs.count(1), signs.count(-1))
    agreement = dominant / len(signs) if signs else 0

    # ==== فلتر الاتجاه V2 ====
    # إذا المجلس يميل لبيع لكن EMA200 صاعد بقوة → يُخفّض ولا يُلغي
    # فقط إذا الفارق كبير والاتجاه قوي نلغي البيع القوي
    trend_adj, vetoed = 0.0, None
    if trend_bias > 0 and final < 0 and last_price > ema200 > 0:
        gap_pct = (last_price - ema200) / ema200 * 100
        if gap_pct > 1.5:
            # سعر أعلى 1.5% فوق EMA200 — بيع صعب وقوي
            trend_adj = +min(15, gap_pct * 4)
            if gap_pct > 3.0:
                vetoed = "فيتو صارم: بيع محظور — سعر فوق EMA200 بأكثر من 3% (اتجاه ماكرو صاعد)"
            elif final < -30 and agreement < 0.75:
                vetoed = "فُّلتر: بيع معاكس لاتجاه صاعد قوي"
    elif trend_bias < 0 and final > 0 and last_price < ema200 > 0:
        gap_pct = (ema200 - last_price) / ema200 * 100
        if gap_pct > 3.0:
            trend_adj = -min(15, gap_pct * 4)
            vetoed = "فيتو صارم: شراء محظور — سعر تحت EMA200 بأكثر من 3% (اتجاه ماكرو هابط)"
        elif gap_pct > 1.5 and final > 30 and agreement < 0.75:
            trend_adj = -min(15, gap_pct * 4)
            vetoed = "فُّلتر: شراء معاكس لاتجاه هابط قوي"

    final += trend_adj

    # بوابات الأمان منفصلة عن التصويت. حدث شديد التأثير يمنع دخولاً جديداً
    # ولا يتحول إلى صوت بيع مصطنع.
    blockers = [r for r in reports if r.flags.get("trade_block")]
    risk_multiplier = min(
        [float(r.flags.get("risk_multiplier", 1.0)) for r in reports] or [1.0]
    )
    if blockers:
        vetoed = "بوابة أحداث: " + "، ".join(r.name for r in blockers)

    # ==== فيتو الانقسام V2 ====
    bulls = [r for r, _ in voting if r.score > 35]
    bears = [r for r, _ in voting if r.score < -35]
    if len(bulls) >= 1 and len(bears) >= 1 and agreement < 0.45 and abs(final) < 35:
        vetoed = (f"انقسام حاد: {len(bulls)} شراء قوي + {len(bears)} بيع قوي "
                  f"— لا يوجد إجماع كافٍ")

    if vetoed:
        final *= 0.25       # يجبر النطاق ضمن -15..+15 (انتظار)
        verdict_label = "انتظار / محايد ⚪ (فيتو)"
        color = "#9e9e9e"
    else:
        verdict_label = next(lbl for th, lbl, _ in THRESHOLDS if final >= th)
        color = next(c for th, _, c in THRESHOLDS if final >= th)

    if active_wsum:
        evidence_quality = sum(r.confidence * w for r, w in active) / active_wsum / 100
    else:
        evidence_quality = 0.0
    confidence = min(95, (40 + abs(final) * 0.55 + agreement * 15) * evidence_quality)
    confidence = max(0, confidence - (15 if vetoed else 0))
    if not STRATEGY_VALIDATED:
        confidence = min(confidence, 60)

    # ==== عتبات الجودة V3 ====
    # 1) درجة أدنى 30 (وليس 15) — إشارة ضعيفة = لا صفقة
    # 2) إجماع حقيقي: 4 وكلاء على الأقل باتجاه واحد (من 8)
    supporting = [r for r, _ in active
                  if (r.score > 10 if final > 0 else r.score < -10)]
    votes_for = len(supporting)
    supporting_families = sorted({EVIDENCE_FAMILY.get(r.key, r.key) for r in supporting})
    min_families = 3
    if abs(final) < 25 or len(supporting_families) < min_families:
        direction = 0
        if not vetoed:
            vetoed = (f"فلتر الجودة: درجة {final:+.1f} أو إجماع "
                      f"{len(supporting_families)} عائلات دون الحد الأدنى "
                      f"(25 / {min_families})")
    else:
        direction = (1 if final > 0 else -1)

    # أي فيتو معلن هو منع تنفيذي مطلق. كان تخفيض الدرجة إلى الربع يسمح
    # نظرياً بمرور إشارة عند الدرجة الحدية +25/-25، خصوصاً مع حدث محظور.
    # لا يجوز أن تنتج بوابة أمان signal قابلاً للتنفيذ مهما بلغت قوة التصويت.
    if vetoed:
        direction = 0

    # بوابة النظام لا تصوت ولا تكرر الفني؛ تسمح فقط بشراء متدرج أو سيولة.
    if direction > 0 and any(r.flags.get("block_long") for r in reports):
        direction = 0
        vetoed = "بوابة الاتجاه المنهجي: الشراء غير مسموح في نظام السيولة"
    elif direction < 0 and any(r.flags.get("block_short") for r in reports):
        direction = 0
        vetoed = "بوابة الاتجاه المنهجي: البيع محظور في استراتيجية long/flat"

    if direction != 0:
        entry = last_price
        stop_dist = max(1.0, 1.3 * atr_value)     # SL = 1.3×ATR
        # R:R إجباري ≈ 1.8:1 — هدف أول 2.3×ATR، هدف ثانٍ 3.5×ATR
        tp1 = entry + direction * 2.3 * atr_value
        tp2 = entry + direction * 3.5 * atr_value
        sl  = entry - direction * stop_dist
        levels = {"direction": "شراء (Long)" if direction > 0 else "بيع (Short)",
                  "entry": round(entry, 1), "sl": round(sl, 1),
                  "tp1": round(tp1, 1), "tp2": round(tp2, 1),
                  "rr": "1 : 1.8 ثم 1 : 2.7"}
    else:
        levels = {"direction": "بدون دخول", "entry": None, "sl": None,
                  "tp1": None, "tp2": None, "rr": "—"}
        verdict_label = "انتظار / محايد ⚪"
        color = "#9e9e9e"

    debate = []
    for r, w in voting:
        stance = ("مع الشراء 🟢"    if r.score > 10 else
                  "مع البيع 🔴"     if r.score < -10 else "ممتنع ⚪")
        debate.append(f"{r.icon} **{r.name}** صوّت: {stance} بدرجة "
                      f"{r.score:+.0f} (ثقة {r.confidence:.0f}%)")

    return {
        "final_score": round(final, 1), "decision": verdict_label, "color": color,
        "confidence": round(confidence, 0), "agreement": round(agreement * 100, 0),
        "levels": levels, "debate": debate,
        "supports": tech_levels.get("supports", []),
        "resistances": tech_levels.get("resistances", []),
        "pivot": tech_levels.get("pivot"),
        "vetoed": vetoed,
        "raw_score": round(final - trend_adj, 1),
        "trend_adj": round(trend_adj, 1),
        "signal": direction,
        "quality_passed": direction != 0,
        "evidence_coverage": round(coverage * 100, 1),
        "evidence_quality": round(evidence_quality * 100, 1),
        "supporting_families": supporting_families,
        "strategy_validated": STRATEGY_VALIDATED,
        "research_only": not STRATEGY_VALIDATED,
        "risk_multiplier": round(max(0.0, min(1.0, risk_multiplier)), 2),
    }


# ===== LLM (اختياري — يرفع جودة مذكرة القرار بشكل ملحوظ) =====
def llm_available():
    return bool(config.get("OPENAI_API_KEY"))


def llm_chairman(reports, decision, news, last_price):
    if not llm_available():
        return None, "لا يوجد OPENAI_API_KEY"
    try:
        from openai import OpenAI
        base_url = config.get("OPENAI_BASE_URL") or None
        model = config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
        client = OpenAI(api_key=config.get("OPENAI_API_KEY"), base_url=base_url)

        brief = "\n".join(
            f"- {r.name}: {r.score:+.0f}/100 بثقة {r.confidence:.0f}% — "
            f"{r.summary} | " + " ; ".join(r.bullets[:3])
            for r in reports)
        headlines = "\n".join(f"• {n['title']} ({n['source']})" for n in news[:15])
        prompt = f"""أنت رئيس مجلس محللين محترفين لتداول الذهب XAU/USD. السعر الفوري {last_price:,.1f}$.
تقارير الوكلاء:
{brief}

أحدث الأخبار:
{headlines}

التصويت الموزون: {decision['final_score']:+.0f}/100 (‘{decision['decision']}’) "
        بثقة {decision['confidence']:.0f}% وفلتر اتجاه: {decision.get('trend_adj',0):+.0f} "
        "{'⚠️ ' + decision['vetoed'] if decision.get('vetoed') else ''}.
المستويات: {decision['levels']}.

اكتب مذكرة 8-12 سطراً بالعربية تتضمن:»
1) خلاصة القرار وسببه في جملتين.
2) أهم خبرين محركين اليوم وكيف أثّرا تاريخياً.
3) الخلاف بين الوكلاء (إن وجد).
4) سيناريو الإبطال: ما الذي يلغي التوصية فوراً؟

كن مباشراً كمتداول محترف."""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=900)
        return resp.choices[0].message.content.strip(), f"✅ {model}"
    except Exception as e:
        return None, f"تعذر استدعاء LLM: {e}"

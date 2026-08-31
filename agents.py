# -*- coding: utf-8 -*-
"""
وكلاء مجلس الذهب — كل وكيل متخصص يصدر تقريراً بدرجة من -100 (بيع أقصى) إلى +100 (شراء أقصى).
"""
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ================================================================ قاموس المشاعر
BULLISH = {
    # إنجليزية
    "rate cut": 3, "cuts rates": 3, "dovish": 2, "fed pivot": 3, "qe": 2,
    "stimulus": 2, "war": 3, "invasion": 3, "escalation": 3, "strike": 2,
    "sanctions": 2, "recession": 3, "crisis": 3, "default": 3, "debt ceiling": 2,
    "safe haven": 2, "safe-haven": 2, "record high": 3, "all-time high": 3,
    "rally": 2, "surge": 2, "jumps": 2, "soars": 2, "central bank buying": 3,
    "gold buying": 2, "weak dollar": 2, "dollar falls": 2, "dollar slides": 2,
    "yields fall": 2, "uncertainty": 1, "inflation rises": 2, "hot inflation": 2,
    "tariffs": 2, "trade war": 3, "etf inflows": 2,
    # عربية
    "خفض الفائدة": 3, "حرب": 3, "تصعيد": 3, "غزو": 3, "عقوبات": 2,
    "ركود": 3, "أزمة": 2, "ملاذ آمن": 2, "مستوى قياسي": 3, "ارتفاع الذهب": 2,
    "صعود الذهب": 2, "تراجع الدولار": 2, "شراء البنوك المركزية": 3,
}
BEARISH = {
    "rate hike": 3, "hawkish": 2, "higher for longer": 3, "strong dollar": 2,
    "dollar rises": 2, "dollar gains": 2, "yields rise": 2, "yields climb": 2,
    "selloff": 3, "sell-off": 3, "plunges": 3, "tumbles": 3, "slumps": 3,
    "drops": 1, "falls": 1, "profit taking": 2, "profit-taking": 2,
    "ceasefire": 3, "peace deal": 3, "truce": 3, "agreement": 1, "deal": 1,
    "easing tensions": 3, "de-escalation": 3, "risk-on": 2, "strong jobs": 2,
    "inflation cools": 2, "etf outflows": 2,
    "رفع الفائدة": 3, "وقف إطلاق النار": 3, "اتفاق سلام": 3, "تهدئة": 3,
    "هبوط الذهب": 2, "انخفاض الذهب": 2, "صعود الدولار": 2, "جنى الأرباح": 2,
}
HIGH_IMPACT = [
    "fomc", "fed decision", "rate decision", "nonfarm", "nfp", "cpi",
    "inflation data", "powell", "emergency", "crash", "plunge", "plummet",
    "payrolls", "jobs report", "قرار الفائدة", "الفيدرالي", "باول",
    "التضخم", "الوظائف", "انهيار",
]

# ذاكرة تاريخية: كيف تفاعل الذهب مع أحداث مشابهة (اقتصادي/عسكري/سياسي)
HISTORICAL_PATTERNS = [
    {"keys": ["ceasefire", "peace deal", "truce", "de-escalation", "وقف إطلاق النار", "اتفاق سلام", "تهدئة"],
     "lesson": "📚 تاريخياً: أخبار وقف إطلاق النار/اتفاقات السلام تضرب الذهب بقوة خلال ساعات (إلغاء علاوة المخاطر الجيوسياسية) — مثل هبوط اليوم الواحد الحاد الذي نشهده أحياناً."},
    {"keys": ["war", "invasion", "escalation", "strike", "حرب", "غزو", "تصعيد"],
     "lesson": "📚 تاريخياً: التصعيد العسكري يدفع الذهب للأعلى فوراً (غزو أوكرانيا 2022 رفع الذهب ~8% في أسابيع؛ أحداث الشرق الأوسط أشعلت قفزات يومية >1.5%)."},
    {"keys": ["rate cut", "dovish", "fed pivot", "خفض الفائدة"],
     "lesson": "📚 تاريخياً: دورات خفض الفائدة الأمريكية هي أقوى محرك صاعد للذهب (دورة 2024 أطلقت موجة قمم تاريخية متتالية)."},
    {"keys": ["hawkish", "higher for longer", "rate hike", "رفع الفائدة"],
     "lesson": "📚 تاريخياً: تشديد الفيدرالي يرفع العائدات والدولار ويضغط على الذهب (Taper Tantrum 2013 أسقط الذهب ~25% في عام)."},
    {"keys": ["central bank buying", "gold buying", "reserves", "شراء البنوك المركزية"],
     "lesson": "📚 تاريخياً: مشتريات البنوك المركزية القياسية منذ 2022 (الصين/بولندا/الهند) شكّلت أرضية صلبة طويلة الأمد تحت السعر."},
    {"keys": ["inflation", "cpi", "التضخم"],
     "lesson": "📚 تاريخياً: مفاجآت التضخم المرتفعة تدعم الذهب كتحوط، لكن إن دفعت الفيدرالي للتشديد فالأثر ينعكس سلباً — السياق هو الحكم."},
    {"keys": ["recession", "crisis", "default", "ركود", "أزمة"],
     "lesson": "📚 تاريخياً: أزمات الركود والديون تطلق موجات ملاذ آمن قوية (أزمة 2008 تلاها تضاعف الذهب خلال 3 سنوات)."},
]


@dataclass
class AgentReport:
    key: str
    name: str
    icon: str
    role: str
    score: float = 0.0            # -100 .. +100
    confidence: float = 50.0      # 0 .. 100
    verdict: str = "محايد"
    summary: str = ""
    bullets: list = field(default_factory=list)
    weight: float = 0.0           # وزن التصويت في المجلس
    flags: dict = field(default_factory=dict)  # بوابات أمان غير اتجاهية


def _verdict(score):
    if score >= 35: return "شراء قوي 🟢"
    if score >= 15: return "شراء 🟢"
    if score > -15: return "محايد ⚪"
    if score > -35: return "بيع 🔴"
    return "بيع قوي 🔴"


def _age_hours(pub, as_of=None):
    """يتسامح مع تواريخ tz-naive و pandas Timestamps و None."""
    if pub is None: return 24.0
    try:
        import pandas as pd
        if isinstance(pub, pd.Timestamp):
            pub = pub.to_pydatetime()
    except Exception:
        pass
    now = as_of or datetime.now(timezone.utc)
    if getattr(now, "tzinfo", None) is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    if getattr(pub, "tzinfo", None) is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return max(0.0, (now - pub).total_seconds() / 3600)


# ================================================= 1) وكيل رصد الأخبار
def news_scout(news, as_of=None):
    bullets = []
    for n in news[:12]:
        age = _age_hours(n["published"], as_of=as_of)
        tag = "🔥" if age < 3 else ("🕐" if age < 12 else "📰")
        bullets.append(f"{tag} [{n['section']}] {n['title']} — {n['source']}")
    return AgentReport(
        key="scout", name="وكيل رصد الأخبار", icon="📡",
        role="يقرأ السوق ويجلب أحدث أخبار الذهب من مصادر عالمية وأمريكية وعربية لحظة بلحظة",
        score=0, confidence=95, verdict="جمع البيانات",
        summary=f"تم رصد {len(news)} خبراً من {len(set(n['source'] for n in news))} مصدراً عالمياً.",
        bullets=bullets)


# ==================================== 2) المحلل الاستراتيجي (أخبار + تاريخ)
def macro_analyst(news, use_llm=False, as_of=None):
    bull = bear = 0.0
    impact_hits, lessons, scored_headlines = [], set(), []
    for n in news:
        t = n["title"].lower()
        age = _age_hours(n["published"], as_of=as_of)
        decay = max(0.25, 1.0 - age / 72)          # الأخبار الأحدث أثقل وزناً
        b = sum(w for k, w in BULLISH.items() if k in t)
        s = sum(w for k, w in BEARISH.items() if k in t)
        if b or s:
            bull += b * decay; bear += s * decay
            scored_headlines.append(
                f"{'🟢' if b > s else '🔴'} {n['title']} "
                f"(قبل {age:.0f} ساعة — {n['source']})")
        if any(k in t for k in HIGH_IMPACT):
            impact_hits.append(f"⚡ خبر عالي التأثير: {n['title']} — {n['source']}")
        for p in HISTORICAL_PATTERNS:
            if any(k in t for k in p["keys"]):
                lessons.add(p["lesson"])
    total = bull + bear
    score = max(-100, min(100, 100 * (bull - bear) / (total + 4)))
    conf = min(90, 35 + total * 4)
    rep = AgentReport(
        key="macro", name="المحلل الاستراتيجي للأخبار", icon="🧠",
        role="يفسّر الأخبار ضمن السياق الاقتصادي والعسكري والسياسي التاريخي الكامل للذهب",
        score=round(score, 1), confidence=round(conf, 0), verdict=_verdict(score),
        summary=(f"حلّل {len(news)} خبراً: قوة شرائية إخبارية {bull:.1f} مقابل "
                 f"قوة بيعية {bear:.1f} (بعد ترجيح حداثة الأخبار)."),
        bullets=(impact_hits[:4] + scored_headlines[:8] + list(lessons)),
        weight=0.30)
    return rep


# ============================================ 3) محلل المؤشرات الفنية
def technical_analyst(df):
    last = df.iloc[-1]; prev = df.iloc[-2]
    pts, bullets = 0.0, []
    # الاتجاه
    if last["close"] > last["ema200"]: pts += 18; bullets.append("✅ السعر فوق EMA200 — اتجاه رئيسي صاعد")
    else: pts -= 18; bullets.append("⛔ السعر تحت EMA200 — اتجاه رئيسي هابط")
    if last["ema20"] > last["ema50"]: pts += 14; bullets.append("✅ EMA20 فوق EMA50 — زخم متوسط صاعد")
    else: pts -= 14; bullets.append("⛔ EMA20 تحت EMA50 — زخم متوسط هابط")
    # MACD
    if last["macd_hist"] > 0 and prev["macd_hist"] <= 0:
        pts += 16; bullets.append("✅ تقاطع MACD إيجابي جديد — إشارة شراء لحظية")
    elif last["macd_hist"] > 0: pts += 8; bullets.append("✅ مدرج MACD موجب")
    elif last["macd_hist"] < 0 and prev["macd_hist"] >= 0:
        pts -= 16; bullets.append("⛔ تقاطع MACD سلبي جديد — إشارة بيع لحظية")
    else: pts -= 8; bullets.append("⛔ مدرج MACD سالب")
    # RSI
    r = last["rsi"]
    if r < 30: pts += 15; bullets.append(f"✅ RSI={r:.0f} تشبع بيعي — فرصة ارتداد")
    elif r > 70: pts -= 15; bullets.append(f"⛔ RSI={r:.0f} تشبع شرائي — خطر جني أرباح")
    elif r > 55: pts += 6; bullets.append(f"✅ RSI={r:.0f} زخم إيجابي معتدل")
    elif r < 45: pts -= 6; bullets.append(f"⛔ RSI={r:.0f} زخم سلبي معتدل")
    else: bullets.append(f"⚪ RSI={r:.0f} محايد")
    # بولينجر
    if last["close"] < last["bb_low"]: pts += 10; bullets.append("✅ السعر تحت الحد السفلي لبولينجر — ارتداد محتمل")
    elif last["close"] > last["bb_up"]: pts -= 10; bullets.append("⛔ السعر فوق الحد العلوي لبولينجر — مبالغة شرائية")
    # ستوكاستك
    if last["stoch_k"] < 20 and last["stoch_k"] > last["stoch_d"]:
        pts += 7; bullets.append("✅ ستوكاستك ينعكس صعوداً من منطقة التشبع البيعي")
    elif last["stoch_k"] > 80 and last["stoch_k"] < last["stoch_d"]:
        pts -= 7; bullets.append("⛔ ستوكاستك ينعكس هبوطاً من منطقة التشبع الشرائي")
    # تغير اليوم
    chg = (last["close"] / last["open"] - 1) * 100 if last["open"] else 0
    if abs(chg) >= 1.0:
        bullets.append(f"⚡ حركة حادة اليوم: {chg:+.2f}% — يوجد خبر محرك للسوق")
    score = max(-100, min(100, pts))
    conf = min(88, 45 + abs(score) * 0.5)
    return AgentReport(
        key="tech", name="محلل المؤشرات الفنية", icon="📈",
        role="يقرأ RSI وMACD والمتوسطات وبولينجر وستوكاستك لحظياً ويخرج بتوافق فني",
        score=round(score, 1), confidence=round(conf, 0), verdict=_verdict(score),
        summary=f"توافق {len(bullets)} إشارة فنية على الفريم اليومي. آخر إغلاق: {last['close']:.1f}$",
        bullets=bullets, weight=0.35)


# ============================================ 4) وكيل إدارة المخاطر
def risk_manager(df, capital=10000, risk_pct=1.0):
    last = df.iloc[-1]
    a = float(last["atr"]); close = float(last["close"])
    atr_pct = a / close * 100
    # نظام التذبذب
    if atr_pct > 2.2:
        score, regime = -25, f"⚠️ تذبذب مرتفع جداً (ATR={atr_pct:.2f}%) — السوق خطر، قلّل الأحجام"
    elif atr_pct > 1.4:
        score, regime = -10, f"🟡 تذبذب متوسط-مرتفع (ATR={atr_pct:.2f}%) — حذر مطلوب"
    else:
        score, regime = 10, f"🟢 تذبذب هادئ (ATR={atr_pct:.2f}%) — بيئة مناسبة للتداول"
    risk_usd = capital * risk_pct / 100
    # R:R إجباري 2:1 — SL أقرب (1.2×ATR) و TP1 أبعد (2.5×ATR)
    stop_dist = 1.2 * a
    target_dist = 2.5 * a
    rr_ratio = target_dist / stop_dist if stop_dist else 0
    oz = risk_usd / stop_dist if stop_dist else 0
    return AgentReport(
        key="risk", name="وكيل إدارة المخاطر", icon="🛡️",
        role="يدرس تذبذب السوق ويحدد نقاط وقف الخسارة وحجم الصفقة الآمن",
        score=score, confidence=85, verdict=regime.split("—")[0].strip(),
        summary=regime,
        bullets=[
            f"📏 ATR(14) = {a:.1f}$ — SL: {stop_dist:.1f}$ (1.2×ATR) | TP1: {target_dist:.1f}$ (2.5×ATR) | R:R={rr_ratio:.2f}:1",
            f"💰 برأس مال {capital:,.0f}$ ومخاطرة {risk_pct}%: الحد الأقصى للخسارة {risk_usd:,.0f}$",
            f"⚖️ حجم الصفقة المقترح: {oz:.2f} أونصة (أو ما يعادلها بالعقود المصغرة)",
            f"🛑 قاعدة ذهبية: لا تخاطر بأكثر من {risk_pct}% في صفقة واحدة مهما كانت الإشارة قوية",
        ], weight=0.15)


# ================================= 5) وكيل استكشاف الخبراء ومواقع التوصيات
EXPERT_SOURCES = [
    ("Kitco News", "https://www.kitco.com", "إنجليزي", "أخبار وتحليلات معادن ثمينة — الأشهر عالمياً"),
    ("FXStreet – XAU/USD", "https://www.fxstreet.com/rates-charts/xauusd", "إنجليزي", "تحليلات فنية وتوقعات يومية للذهب"),
    ("DailyFX Gold", "https://www.dailyfx.com/gold-price", "إنجليزي", "تحليل مؤسسي + مؤشر معنويات المتداولين"),
    ("TradingView – أفكار XAUUSD", "https://www.tradingview.com/symbols/XAUUSD/ideas/", "متعدد", "آلاف توصيات المحللين المستقلين لحظياً"),
    ("Investing.com – تحليلات الذهب", "https://www.investing.com/commodities/gold", "متعدد", "تحليلات فنية وأساسية وتوصيات"),
    ("World Gold Council", "https://www.gold.org", "إنجليزي", "بيانات الطلب والبنوك المركزية — المصدر المرجعي"),
    ("BullionVault News", "https://www.bullionvault.com/gold-news", "إنجليزي", "تحليل سوق السبائك المؤسسي"),
    ("GoldSeek", "https://goldseek.com", "إنجليزي", "تجميع مقالات كبار محللي الذهب"),
    ("Jin10 金十数据", "https://www.jin10.com", "صيني 🇨🇳", "كنز صيني: أسرع فلاش إخباري مالي في آسيا — يكشف تحركات التدفقات الآسيوية قبل الغرب"),
    ("FX168 财经", "https://www.fx168.com", "صيني 🇨🇳", "تحليلات عملات ومعادن من السوق الصيني (أكبر مستهلك للذهب)"),
    ("ProFinance.ru", "https://www.profinance.ru", "روسي 🇷🇺", "كنز روسي: تحليلات فنية عميقة للذهب والعملات بعيداً عن الإعلام الغربي"),
    ("Moneycontrol – Gold", "https://www.moneycontrol.com/news/business/commodities/", "هندي 🇮🇳", "نبض السوق الهندي (ثاني أكبر مستهلك) — موسم الأعراس والمهرجانات يحرك الطلب"),
    ("Economic Times – Gold", "https://economictimes.indiatimes.com/commoditysummary/symbol-GOLD.cms", "هندي 🇮🇳", "أسعار وتحليلات MCX الهندية"),
    ("مباشر Mubasher", "https://www.mubasher.info", "عربي 🇸🇦", "أخبار وتحليلات الذهب بالعربية"),
    ("أرقام Argaam", "https://www.argaam.com", "عربي 🇸🇦", "تغطية خليجية للمعادن والأسواق"),
]


def expert_scout(news):
    forecast_words = ["forecast", "prediction", "outlook", "price target", "analysis",
                      "expects", "توقعات", "تحليل", "مستهدف"]
    hits, bull, bear = [], 0.0, 0.0
    for n in news:
        t = n["title"].lower()
        if any(w in t for w in forecast_words):
            b = sum(w_ for k, w_ in BULLISH.items() if k in t)
            s = sum(w_ for k, w_ in BEARISH.items() if k in t)
            bull += b; bear += s
            hits.append(f"🎯 {n['title']} — {n['source']}")
    total = bull + bear
    score = max(-100, min(100, 100 * (bull - bear) / (total + 3))) if total else 0
    bullets = hits[:6] if hits else ["لم تُرصد توقعات صريحة اليوم — راجع دليل المصادر أدناه"]
    bullets.append("——— 🌐 دليل مصادر الخبراء (الغربية + كنوز الصين وروسيا والهند) ———")
    bullets += [f"🔗 {nm} ({lng}) — {desc}: {url}" for nm, url, lng, desc in EXPERT_SOURCES]
    return AgentReport(
        key="expert", name="وكيل مستكشف الخبراء", icon="🌐",
        role="يبحث في أهم مواقع التوصيات والخبراء عالمياً — الغربية والصينية والروسية والهندية والعربية",
        score=round(score, 1), confidence=60 if total else 40, verdict=_verdict(score),
        summary=(f"رصد {len(hits)} توقعاً/تحليلاً منشوراً للخبراء اليوم. "
                 f"الميزان: {bull:.0f} إيجابي / {bear:.0f} سلبي."),
        bullets=bullets, weight=0.20)

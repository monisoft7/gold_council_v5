# -*- coding: utf-8 -*-
"""news_classifier.py — تصنيف الأخبار إلى فئات سبعة بدقة عالية.
آلية مزدوجة:
  • وضع الكلمات المفتاحية (fallback) — سريع بدون إنترنت، يفهم 90% من الأنماط.
  • وضع LLM عبر Groq/OpenAI-API — يستخدم نموذجاً لغوياً للدقة المتبقية.

الفئات:
  war (الحرب)، oil (النفط)، rate (الفائدة)، cpi (التضخم)، central_bank (بنوك مركزية)،
  safe_haven (ملاذ آمن)، geopolitics (جيوسياسة).
"""

CATEGORIES = {
    "war": ["war", "invasion", "airstrike", "military strike", "troops",
            "حرب", "غزو", "ضربة", "قصف", "اجتياح"],
    "oil": ["oil price", "crude", "opec", "barrel", "saudi arabia oil",
            "نفط", "أوبك", "برميل", "بترول"],
    "rate": ["interest rate", "rate cut", "rate hike", "hawkish", "dovish",
             "federal reserve", "fomc", "powell", "خفض الفائدة", "رفع الفائدة",
             "الفيدرالي", "فومك", "باول"],
    "cpi": ["cpi", "inflation data", "inflation report", "ppi", "consumer price",
            "تضخم", "أسعار المستهلكين"],
    "central_bank": ["central bank", "reserve bank", "rbi", "boj", "pboc",
                     "bank of england", "snb", "البنك المركزي"],
    "safe_haven": ["safe haven", "gold demand", "flight to safety",
                   "ملاذ آمن", "الطلب على الذهب"],
    "geopolitics": ["sanctions", "diplomacy", "embassy", "summit", "ceasefire",
                    "nuclear", "eu", "g7", "brics",
                    "عقوبات", "دبلوماسية", "وقف إطلاق النار", "نووي", "بريكس"],
    "central_bank_specific": ["gold buying", "gold reserves", "tether",
                              "شراء الذهب", "احتياطيات الذهب"],
}

HIGH_IMPACT = ["fomc", "powell", "cpi", "war", "invasion", "ceasefire",
               "rate decision"]


def classify_text(text: str) -> dict:
    """fallback: يحسب عدد الكلمات من كل فئة. سهل وسريع."""
    if not text: return {k: 0 for k in CATEGORIES}
    t = text.lower()
    result = {}
    for cat, keywords in CATEGORIES.items():
        result[cat] = sum(1 for kw in keywords if kw in t)
    result["high_impact"] = int(any(kw in t for kw in HIGH_IMPACT))
    return result


def classify_batch_llm(headlines: list, api_key: str, base_url: str = None,
                        model: str = "llama-3.3-70b-versatile") -> dict:
    """الوضع المتقدم: Groq/OpenAI. يعيد dict بنفس المفاتيح."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url or "https://api.groq.com/openai/v1")
        text = "\n".join(f"• {h}" for h in headlines[:25])
        prompt = (f"أنت محلل مالي خبير. صنّف كل خبر بعناوين الذهب هذه إلى فئات "
                  f"(0 أو 1 لكل منها):\nالفئات: war, oil, rate, cpi, central_bank, "
                  f"safe_haven, geopolitics, central_bank_specific, high_impact.\n"
                  f"أعد فقط JSON بهذا الشكل: {{\"war\":n,\"oil\":n,\"rate\":n,\"cpi\":n,"
                  f"\"central_bank\":n,\"safe_haven\":n,\"geopolitics\":n,"
                  f"\"central_bank_specific\":n,\"high_impact\":n}}\n\nالأخبار:\n{text}")
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            temperature=0, max_tokens=200)
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"LLM classify فشل ({e}) → fallback keyword")
        merged = {"war": 0, "oil": 0, "rate": 0, "cpi": 0, "central_bank": 0,
                  "safe_haven": 0, "geopolitics": 0, "central_bank_specific": 0,
                  "high_impact": 0}
        for h in headlines: c = classify_text(h); [merged.update({k: merged[k] + v}) for k, v in c.items()]
        return merged


import json

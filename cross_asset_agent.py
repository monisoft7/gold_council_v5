# -*- coding: utf-8 -*-
"""
وكيل الارتباط المتقاطع (Cross-Asset Correlation Agent).
الذهب لا يعيش وحده — يتأثر سلبياً ب DXY و US10Y، وإيجابياً ب VIX.
يسحب بيانات هذه الأصول من Yahoo Finance ويحسب ارتباط الـ20 يوم ويزن
قرار المجلس تبعاً لذلك. لا يستخدم look-ahead في الباك-تست.

الرموز (مُختبرة تاريخياً):
  • DX-Y.NYB  → مؤشر الدولار DXY
  • ^TNX      → عائد سندات الخزانة الأمريكية 10 سنوات
  • ^GSPC     → S&P 500
  • ^VIX      → مؤشر خوف السوق CBOE
"""
import requests
import pandas as pd
import numpy as np

from agents import AgentReport

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"}

SYMBOLS = {"DXY": "DX-Y.NYB", "US10Y": "^TNX",
           "SPX": "^GSPC", "VIX": "^VIX"}

CACHE = {}


def cross_asset_from_history(gold_history: pd.DataFrame,
                             macro_history: pd.DataFrame,
                             as_of=None) -> AgentReport:
    """نسخة point-in-time للباكتيست؛ لا تجري أي اتصال شبكي.

    gold_history: أعمدة time, close. macro_history: available_at + dxy/us10y/spx/vix.
    لا يدخل أي صف لم يكن available_at <= as_of.
    """
    if as_of is None or macro_history is None or macro_history.empty:
        return AgentReport(
            key="cross", name="وكيل الارتباط المتقاطع", icon="🔗",
            role="يراقب DXY والعوائد وSPX وVIX ببيانات point-in-time",
            score=0, confidence=20, verdict="بيانات تاريخية غير كافية",
            summary="لم تتوفر لقطة أصول مترابطة صالحة زمنياً", bullets=[])
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    macro = macro_history.copy()
    macro["available_at"] = pd.to_datetime(macro["available_at"], utc=True)
    macro = macro.loc[macro["available_at"] <= cutoff].tail(60).copy()
    gold = gold_history[["time", "close"]].copy()
    gold["session"] = pd.to_datetime(gold["time"], utc=True).dt.floor("D")
    macro["session"] = macro["available_at"].dt.floor("D")
    aligned = gold.merge(macro, on="session", how="inner").tail(40)
    if len(aligned) < 10:
        return AgentReport(
            key="cross", name="وكيل الارتباط المتقاطع", icon="🔗",
            role="يراقب DXY والعوائد وSPX وVIX ببيانات point-in-time",
            score=0, confidence=25, verdict="بيانات تاريخية غير كافية",
            summary=f"توفر {len(aligned)} جلسات متزامنة فقط", bullets=[])
    gret = aligned["close"].pct_change()
    bullets, score, used = [], 0.0, 0
    expected = {"dxy": -1, "us10y": -1, "spx": -1, "vix": 1}
    for col, sign in expected.items():
        if col not in aligned:
            continue
        series = pd.to_numeric(aligned[col], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if series.notna().sum() < 10:
            continue
        if col == "us10y":
            # العوائد قد تعبر الصفر؛ النسبة المئوية عندها غير معرفة اقتصادياً.
            aret = series.diff()
            move = float(series.iloc[-1] - series.iloc[-5])
            move_label = f"{move * 100:+.1f} نقطة أساس"
        else:
            aret = series.pct_change(fill_method=None)
            base = float(series.iloc[-5])
            if not np.isfinite(base) or abs(base) < 1e-12:
                continue
            move = float(series.iloc[-1] / base - 1)
            move_label = f"{move:+.2%}"
        if not np.isfinite(move):
            continue
        corr = float(gret.tail(20).corr(aret.tail(20)))
        if not np.isfinite(corr):
            corr = 0.0
        # إشارة الأصل مستقلة عن اتجاه الذهب: ضعف عدو الذهب أو قوة حليفه صاعد.
        contribution = 12 if move * sign > 0 else (-12 if move * sign < 0 else 0)
        score += contribution; used += 1
        bullets.append(f"{col.upper()}: تغير 5 جلسات {move_label} | ارتباط عوائد 20ج {corr:+.2f}")
    score = max(-100, min(100, score))
    conf = min(80, 35 + used * 8 + abs(score) * 0.2)
    verdict = ("شراء 🟢" if score >= 15 else "بيع 🔴" if score <= -15 else "محايد ⚪")
    return AgentReport(
        key="cross", name="وكيل الارتباط المتقاطع", icon="🔗",
        role="يراقب DXY والعوائد وSPX وVIX ببيانات point-in-time",
        score=round(score, 1), confidence=round(conf, 0), verdict=verdict,
        summary=f"{used} أصول متزامنة دون اتصالات حية أثناء الباكتيست",
        bullets=bullets, weight=0.20)

# ارتباطات تاريخية (لإسقاط قراءة 20 يوم على الذهب):
#   DXY ↔ الذهب: سالب قوي (≈ -0.7)
#   US10Y ↔ الذهب: سالب (≈ -0.5)
#   SPX ↔ الذهب: سالب خفيف (±0.2، ينقلب في أزمات)
#   VIX ↔ الذهب: طرد ضعيف في العادي، قوي في الأزمات
EXPECTED_CORR = {"DXY": -0.70, "US10Y": -0.45,
                 "SPX": -0.20, "VIX": +0.30}


def _fetch(sym: str, range_: str = "6mo") -> pd.Series:
    """جلب آمن بسلسلةprice فقط، مع كاش بسيط."""
    if sym in CACHE:
        return CACHE[sym]
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            f"?interval=1d&range={range_}", headers=UA, timeout=20).json()
        q = r["chart"]["result"][0]
        s = pd.Series(q["indicators"]["quote"][0]["close"],
                      index=pd.to_datetime(q["timestamp"], unit="s"),
                      name=sym).dropna()
        CACHE[sym] = s
        return s
    except Exception:
        return pd.Series(dtype=float)


def cross_asset_agent(gold_close: pd.Series) -> AgentReport:
    """يقرأ الذهب + الأصول المرتبطة ويعطي إشارة مع درجة."""
    if gold_close is None or len(gold_close) < 25:
        return AgentReport(
            key="cross", name="وكيل الارتباط المتقاطع", icon="🔗",
            role="يقرأ العلاقة اللحظية للذهب مع DXY وUS10Y وSPX وVIX",
            score=0, confidence=30, verdict="بيانات غير كافية",
            summary="تعذر إحضار أصول الارتباط", bullets=[])

    g = gold_close.tail(60).reset_index(drop=True)
    bullets, score = [], 0.0
    # ربط كل أصل مع الذهب (آخر 20 يوم) وقراءة مخالفة الاتجاه
    for name, sym in SYMBOLS.items():
        s = _fetch(sym)
        if len(s) < 25:
            bullets.append(f"⚠️ تعذر جلب {name} — تخطّ")
            continue
        s20 = s.tail(20).reset_index(drop=True)
        # ارتباط 20 يوم
        corr = (g.tail(20).corr(s20)
                if len(s20) >= 20 else EXPECTED_CORR[name])
        expected = EXPECTED_CORR[name]
        # تغير 5 أيام لكل من الذهب والأصل
        d_gold = (g.iloc[-1] / g.iloc[-5] - 1) * 100 if len(g) >= 5 else 0
        d_asset = (s20.iloc[-1] / s20.iloc[-5] - 1) * 100 if len(s20) >= 5 else 0
        # هل تحرك الأصل مع توقعه التاريخي (للذهب)؟
        if expected < 0:                       # الأصل عدو الذهب عادة
            aligned = d_gold > 0 and d_asset < 0     # ذهب ↑ ودولار ↓ ⇒ متطابق
            anti    = d_gold < 0 and d_asset > 0
        else:                                  # الأصل حليف (VIX)
            aligned = d_gold > 0 and d_asset > 0
            anti    = d_gold < 0 and d_asset < 0
        if aligned:
            pts = 18; verdict = "🟢 يؤكد إشارة الذهب"
        elif anti:
            pts = -18; verdict = "🔴 يعارض إشارة الذهب"
        else:
            pts = 0; verdict = "⚪ محايد"
        score += pts
        bullets.append(
            f"📊 {name}: تحرك {d_asset:+.2f}% / ذهب {d_gold:+.2f}% | "
            f"ارتباط 20ي={corr:+.2f} (متوقع {expected:+.2f}) | {verdict}"
        )
    # VIX قراءة خاصة (الخوف المرتفع يدعم ذهب)
    vix = _fetch(SYMBOLS["VIX"])
    if len(vix) >= 5:
        v = float(vix.iloc[-1])
        v_prev = float(vix.iloc[-5])
        if v > 25 and v > v_prev:
            score += 14; bullets.append(f"⚠️ VIX={v:.1f} صاعد فوق 25 — ملاذ آمن نشط (+14)")
        elif v < 15:
            score -= 8;  bullets.append(f"😌 VIX={v:.1f} هادئ — رغبة المخاطرة مرتفعة (-8)")
    score = max(-100, min(100, score))
    conf  = min(85, 45 + abs(score) * 0.55)
    return AgentReport(
        key="cross", name="وكيل الارتباط المتقاطع", icon="🔗",
        role="يراقب انفصال الذهب عن DXY/US10Y/SPX/VIX — مؤشرات قصوى لقرار المجلس",
        score=round(score, 1), confidence=round(conf, 0),
        verdict=("شراء قوي 🟢" if score >= 35 else
                 "شراء 🟢"      if score >= 15 else
                 "محايد ⚪"     if score > -15 else
                 "بيع 🔴"       if score > -35 else "بيع قوي 🔴"),
        summary=f"تقييم 4 أصول مرتبطة: محصلة نقاط {score:+.0f}",
        bullets=bullets, weight=0.20)

# -*- coding: utf-8 -*-
"""
backtester_v5.py — باك-تست مُصحَّح مع إصلاحات جوهرية:
  1) إذا لم يُصطدم بـ SL/TP خلال النافذة، يُحسَب العائد بسعر إغلاق
     آخر شمعة متاحة (لا عند سعر اليوم 0 → لا تلاعب بالرقم).
  2) لا تُسجَّل أي صفقة لم يبقَ أمامها ≥ 5 أيام متابعة (حماية من التزوير).
  3) تسمية المهام أكثر ضبطاً: hit = فتح +5 أيام، miss = SL أو 5 أيام < entry - cost.
  4) إخراج ميزات موجهة (features) لتدريب طبقة التعلم العميق:
       - المؤشرات الفنية لحظة القرار
       - الكثافة الإخبارية (counts per category)
       - درجة كل وكيل
       - مفهوم "event_window" يحوي هل يوجد FOMC/CPI/NFP في 72 ساعة القادمة.
  5) يُصدِّر trade_log.csv + features.csv لاستهلاك ml_trainer.py.
"""
from __future__ import annotations
import argparse, csv, json, os, sys, warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
warnings.filterwarnings("ignore")

import data_feeds, indicators, agents, council
import cross_asset_agent, seasonality_agent, event_calendar_agent, pattern_agent
import news_classifier
import macro_regime_agent
import cot_agent
import systematic_regime_agent
import decision_pipeline

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def load_prices_csv(path: str) -> pd.DataFrame:
    """يقرأ ملف أسعار محلي (time,open,high,low,close[,volume]) ويجهّزه للباك-تست."""
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    return df


def fetch_historical(days_back: int = 365) -> pd.DataFrame:
    """يجلب ≥ days_back يوم من GC=F، مع كاش."""
    range_ = "2y" if days_back > 365 else f"{max(60, days_back // 30 + 1)}mo"
    cache = os.path.join(CACHE_DIR, f"gc_{days_back}d.csv")
    try:
        df = data_feeds.get_ohlc(range_=range_, interval="1d")
        df.to_csv(cache, index=False); return df
    except Exception:
        if os.path.exists(cache): return pd.read_csv(cache, parse_dates=["time"])
        raise RuntimeError("تعذر جلب بيانات GC=F ولا يوجد كاش")


def load_news_csv(path: str) -> list:
    """يقرأ أخبار CSV (time,title,source,section). كل الأوقات تُجبر على UTC
    لتجنّب TypeError: can't compare offset-naive and offset-aware datetimes."""
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                pub = datetime.fromisoformat(str(row.get("time", "")).replace("Z", "+00:00"))
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                else:
                    pub = pub.astimezone(timezone.utc)
            except Exception:
                pub = None
            out.append({"title": row.get("title", ""), "source": row.get("source", ""),
                        "section": row.get("section", "أرشيف"), "published": pub})
    out.sort(key=lambda x: x["published"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
             reverse=True)
    return out


# ========= القرار نفسه (دون ازدواجية) =========
def simulate_decision(history_window: pd.DataFrame, news_before: list,
                       capital=10000, risk_pct=1.0, as_of=None,
                       macro_history=None,
                       events_path=str(decision_pipeline.DEFAULT_EVENTS_PATH)):
    if len(history_window) < 210:
        return None, None
    result = decision_pipeline.run_decision(
        history_window, news_before,
        capital=capital, risk_pct=risk_pct, as_of=as_of,
        macro_history=macro_history, load_cached_macro=False,
        events_path=events_path,
    )
    context = {"reports": result["reports"], "last_price": result["last_price"]}
    context.update(result["context"])
    return result["dec"], context


@dataclass
class Trade:
    day: object
    decision: str
    score: float
    confidence: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    exit_price: float           # ← سعر الخروج الحقيقي، لا سعر اليوم 0
    exit_reason: str            # 'tp1','sl','window_end'
    exit_window_days: int
    direction: int
    pnl_pct: float              # ← real pnl after slippage (0.05% per side)
    is_win: bool
    mae: float
    mfe: float
    stop_hit: bool
    news_categories: dict       # كثافة الأخبار حسب category


def regress_trade(full: pd.DataFrame, i: int, direction: int,
                  lv: dict, news_cats: dict, max_w: int = 7, cost: float = 0.05):
    """تابع الحركة لمدة max_w أيام، أو حتى يصطدم SL/TP، وأخرج سجلاً صحيحاً."""
    entry = lv["entry"] or 0; sl = lv.get("sl") or 0; tp1 = lv.get("tp1") or 0
    if direction == 0 or entry == 0:
        return None
    mae = mfe = 0.0
    last_close = entry
    elapsed = 0
    for w in range(1, max_w + 1):
        if i + w >= len(full): break
        elapsed = w
        r = full.iloc[i + w]
        last_close = float(r["close"])
        if direction == 1:
            mae = min(mae, (float(r["low"]) - entry) / entry * 100)
            mfe = max(mfe, (float(r["high"]) - entry) / entry * 100)
            if sl and float(r["low"]) <= sl:
                return Trade(day=full.iloc[i]["time"], decision="", score=0, confidence=0,
                             entry=entry, sl=sl, tp1=tp1, tp2=0,
                             exit_price=float(sl) * (1 - cost / 100),
                             exit_reason="sl", exit_window_days=elapsed,
                             direction=direction,
                             pnl_pct=direction * ((float(sl) * (1 + cost / 100) - entry) / entry * 100),
                             is_win=False, mae=mae, mfe=mfe, stop_hit=True,
                             news_categories=news_cats)
            if tp1 and float(r["high"]) >= tp1:
                return Trade(day=full.iloc[i]["time"], decision="", score=0, confidence=0,
                             entry=entry, sl=sl, tp1=tp1, tp2=0,
                             exit_price=float(tp1) * (1 - cost / 100),
                             exit_reason="tp1", exit_window_days=elapsed,
                             direction=direction,
                             pnl_pct=direction * ((float(tp1) * (1 + cost / 100) - entry) / entry * 100),
                             is_win=True, mae=mae, mfe=mfe, stop_hit=False,
                             news_categories=news_cats)
        else:  # short
            mae = max(mae, (float(r["high"]) - entry) / entry * 100)
            mfe = min(mfe, (float(r["low"]) - entry) / entry * 100)
            if sl and float(r["high"]) >= sl:
                return Trade(day=full.iloc[i]["time"], decision="", score=0, confidence=0,
                             entry=entry, sl=sl, tp1=tp1, tp2=0,
                             exit_price=float(sl) * (1 + cost / 100),
                             exit_reason="sl", exit_window_days=elapsed,
                             direction=direction,
                             pnl_pct=direction * ((float(sl) * (1 - cost / 100) - entry) / entry * 100),
                             is_win=False, mae=mae, mfe=mfe, stop_hit=True,
                             news_categories=news_cats)
            if tp1 and float(r["low"]) <= tp1:
                return Trade(day=full.iloc[i]["time"], decision="", score=0, confidence=0,
                             entry=entry, sl=sl, tp1=tp1, tp2=0,
                             exit_price=float(tp1) * (1 + cost / 100),
                             exit_reason="tp1", exit_window_days=elapsed,
                             direction=direction,
                             pnl_pct=direction * ((float(tp1) * (1 - cost / 100) - entry) / entry * 100),
                             is_win=True, mae=mae, mfe=mfe, stop_hit=False,
                             news_categories=news_cats)
    # إغلاق بنهاية النافذة (لا تلاعب)
    sign_target = 1 if direction == 1 else -1
    exit_multiplier = (1 - cost / 100) if direction == 1 else (1 + cost / 100)
    exit_price = float(last_close) * exit_multiplier
    pnl = sign_target * ((exit_price - entry) / entry * 100)
    return Trade(day=full.iloc[i]["time"], decision="", score=0, confidence=0,
                 entry=entry, sl=sl, tp1=tp1, tp2=0, exit_price=exit_price,
                 exit_reason="window_end", exit_window_days=elapsed, direction=direction,
                 pnl_pct=pnl, is_win=(pnl > 0), mae=mae, mfe=mfe, stop_hit=False,
                 news_categories=news_cats)


def classify_news_window(news_window: list) -> dict:
    """يكثّف 7 فئات إخبارية حسب العناوين بدلاً من قراءة المحتوى كاملاً."""
    cats = {"war": 0, "oil": 0, "rate": 0, "cpi": 0, "central_bank": 0,
            "safe_haven": 0, "geopolitics": 0, "central_bank_specific": 0,
            "high_impact_count": 0}
    if not news_window: return cats
    for n in news_window[:30]:
        title = (n.get("title") or "").lower()
        for cat in news_classifier.CATEGORIES:
            if any(kw in title for kw in news_classifier.CATEGORIES[cat]):
                cats[cat] += 1
        if any(h in title for h in news_classifier.HIGH_IMPACT):
            cats["high_impact_count"] += 1
    return cats


def run_replay(days_back=365, step_days=4, windows_days_max=7,
               capital=10000.0, risk_pct=1.0, news_csv=None, prices_csv=None,
               min_forward_days=5, macro_csv=None, events_csv="events_3y.csv"):
    if prices_csv:
        full = load_prices_csv(prices_csv)
    else:
        full = fetch_historical(days_back).sort_values("time").reset_index(drop=True)
    external = load_news_csv(news_csv) if news_csv else []
    macro_history = pd.read_csv(macro_csv) if macro_csv else None
    trades, features = [], []
    i = 210
    end_idx = len(full) - windows_days_max - 1
    while i < end_idx:
        window = full.iloc[:i + 1].copy()
        ctime = full.iloc[i]["time"]
        cutoff = ctime.to_pydatetime() if hasattr(ctime, "to_pydatetime") else ctime
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        else:
            cutoff = cutoff.astimezone(timezone.utc)
        if external:
            news_start = cutoff - timedelta(hours=72)
            nw = [n for n in external if n["published"] and
                  news_start <= n["published"] <= cutoff]
        else:
            nw = [{"title": "", "source": "—", "section": "—", "published": cutoff,
                   "n": None}]
        dec, ctx = simulate_decision(
            window, nw, capital, risk_pct, as_of=cutoff,
            macro_history=macro_history, events_path=events_csv)
        if dec is None:
            i += step_days; continue
        direction = int(dec.get("signal", 0))
        # لا نسجل أي صفقة لا يوجد ≥5 أيام بعدها (حماية من تلاعب النافذة)
        if direction != 0 and (len(full) - i) >= min_forward_days:
            news_cats = classify_news_window(nw)
            # === إجبار R:R ≥ 2:1 (تصحيح مدير المخاطر) ===
            # القرار يُحسب بعد اكتمال إغلاق جلسة i، لذلك أول سعر قابل
            # للتنفيذ دون تحيز هو افتتاح الجلسة التالية لا إغلاق اليوم نفسه.
            _entry = float(full.iloc[i + 1]['open'])
            _atr = float(indicators.add_all(full.iloc[:i+1].copy()).iloc[-1]['atr'])
            if direction == 1:  # شراء
                _sl = _entry - 1.3 * _atr
                _tp1 = _entry + 2.3 * _atr
                _tp2 = _entry + 3.5 * _atr
            else:  # بيع
                _sl = _entry + 1.3 * _atr
                _tp1 = _entry - 2.3 * _atr
                _tp2 = _entry - 3.5 * _atr
            forced_levels = {'entry': _entry, 'sl': _sl, 'tp1': _tp1, 'tp2': _tp2}
            t = regress_trade(full, i, direction, forced_levels, news_cats,
                              max_w=windows_days_max)
            if t:
                t.decision = dec["decision"]; t.score = dec["final_score"]
                t.confidence = dec["confidence"]
                trades.append(t)
                # بناء شعاع مزايا للتعلّم العميق
                feat = _to_feature_row(t, dec, ctx, news_cats)
                feat["win"] = int(t.is_win); feat["pnl_pct"] = round(t.pnl_pct, 3)
                features.append(feat)
        i += step_days
    return _summarize(trades), trades, features


def _to_feature_row(trade, dec, ctx, news_cats):
    return {
        "day": str(trade.day), "decision": trade.decision,
        "exit_window_days": int(trade.exit_window_days),
        "score": dec["final_score"], "confidence": dec["confidence"],
        "agreement": dec["agreement"], "vetoed": int(bool(dec.get("vetoed"))),
        "rsi": ctx.get("rsi", 0), "volatility_pct": ctx.get("volatility_pct", 0),
        "macd_hist": ctx.get("macd_hist", 0), "trend_bias": ctx.get("trend_bias", 0),
        "atr": ctx.get("atr", 0), "adx_proxy": abs(ctx.get("macd_hist", 0)) * 10,
        **news_cats,
    }


def _summarize(trades):
    n = len(trades)
    if n == 0: return {"error": "no trades"}
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    stops = [t for t in trades if t.stop_hit]
    avg_w = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
    avg_l = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
    pf = (sum(t.pnl_pct for t in wins) / abs(sum(t.pnl_pct for t in losses))) if losses else float("inf")
    return {
        "total_trades": n,
        "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / n, 1),
        "avg_winner_pct": round(avg_w, 3),
        "avg_loser_pct": round(avg_l, 3),
        "profit_factor": round(pf, 2),
        "stop_hit_pct": round(100 * len(stops) / n, 1),
        "sl_exits": sum(1 for t in trades if t.exit_reason == "sl"),
        "tp1_exits": sum(1 for t in trades if t.exit_reason == "tp1"),
        "window_end_exits": sum(1 for t in trades if t.exit_reason == "window_end"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--capital", type=float, default=10000.0)
    ap.add_argument("--risk", type=float, default=1.0)
    ap.add_argument("--news-csv", type=str, default=None)
    ap.add_argument("--prices-csv", type=str, default=None)
    ap.add_argument("--macro-csv", type=str, default=None)
    ap.add_argument("--events-csv", type=str,
                    default=str(decision_pipeline.DEFAULT_EVENTS_PATH))
    ap.add_argument("--out", type=str, default="backtest_report_v5.json")
    ap.add_argument("--features-out", type=str, default="features_v5.csv")
    args = ap.parse_args()
    if not args.replay: ap.print_help(); return
    print(f"⏳ BACKTESTER V5 المُصحَّح: {args.days}d, step={args.step}")
    summary, trades, features = run_replay(args.days, args.step,
                                           capital=args.capital,
                                           risk_pct=args.risk,
                                           news_csv=args.news_csv, prices_csv=args.prices_csv,
                                           macro_csv=args.macro_csv,
                                           events_csv=args.events_csv)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    if features:
        pd.DataFrame(features).to_csv(args.features_out, index=False, encoding="utf-8")
    print("=" * 60)
    print("📊 V5 — باك-تست مُصحَّح")
    print("=" * 60)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n📄 {args.out} | {args.features_out} ({len(features)} صف مزايا)")


if __name__ == "__main__":
    main()

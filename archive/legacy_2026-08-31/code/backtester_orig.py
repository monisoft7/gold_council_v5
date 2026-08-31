# -*- coding: utf-8 -*-
"""
وحدة الباك-تست التاريخي لمجلس الذهب.
يقيس دقة توصيات المجلس على بيانات تاريخية حقيقية للذهب GC=F (Yahoo Finance).

المميزات:
  * يعيد استخدام نفس دوال التوصية في council.py (لا نسخة موازية)
  * منع look-ahead bias: الوكلاء يستخدمون فقط الأخبار المتاحة قبل زمن القرار،
    والمؤشرات الفنية تستخدم الشموع حتى اليوم فقط
  * يقيس: hit rate اتجاهي، متوسط الحركة بعدة نوافذ (1 يوم/3 أيام/7 أيام)،
    MAE/MFE، نسبة وقف الخسارة المفعّل، P&L افتراضي، وأفضل/أصعب قرار
  * مصدر البيانات: Yahoo Finance (مُختبر فعلياً)، مع كاش CSV محلي.
    يدعم أيضاً رفع CSV خارجي عند عدم وجود إنترنت أو عدم توفر Yahoo.
  * يعمل كـ CLI عبر:  python backtester.py --replay --days 180
"""
from __future__ import annotations
import argparse, csv, json, os, sys, warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore")

import data_feeds
import indicators
import cross_asset_agent
import seasonality_agent
import event_calendar_agent
import pattern_agent
import agents
import council

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# ============================================================ مصدر البيانات
def fetch_historical_days(years: int = 2) -> pd.DataFrame:
    """يجلب ~2 سنة من بيانات جدول GC=F مع كاش CSV محلي."""
    cache = os.path.join(CACHE_DIR, f"gc_daily_{years}y.csv")
    try:
        df = data_feeds.get_ohlc(range_=f"{years}y", interval="1d")
        df.to_csv(cache, index=False)
        return df
    except Exception as e:
        if os.path.exists(cache):
            return pd.read_csv(cache, parse_dates=["time"])
        raise RuntimeError(f"تعذر جلب البيانات التاريخية ولا يوجد كاش: {e}")


def load_news_csv(path: str) -> list:
    """يحمّل ملف CSV خارجي للأخبار التاريخية بصيغة:
       time,title,source,section"""
    out = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                pub = datetime.fromisoformat(row["time"])
            except Exception:
                pub = None
            out.append({"title": row.get("title", ""),
                        "source": row.get("source", ""),
                        "section": row.get("section", "أرشيف"),
                        "published": pub})
    out.sort(key=lambda x: x["published"] or datetime(1970,1,1), reverse=True)
    return out


# =========================================================== محاكي الوكلاء
def simulate_decision(history_window: pd.DataFrame, news_before: list,
                       capital: float, risk_pct: float):
    """كما يفعل المجلس على البيانات اللحظية، لكن مع نافذة تاريخية +
    أخبار مرشحّة قبل نقطة زمنية محددة (لا look-ahead)."""
    df = indicators.add_all(history_window.copy())
    if len(df) < 210:
        return None, "بيانات غير كافية لحساب EMA200"
    levels = indicators.support_resistance(df)
    last = float(df.iloc[-1]["close"])
    atr = float(df.iloc[-1]["atr"])

    reports = [
        agents.news_scout(news_before),
        agents.macro_analyst(news_before),
        agents.technical_analyst(df),
        cross_asset_agent.cross_asset_agent(df.set_index("time")["close"]),
        seasonality_agent.seasonality_agent(df),
        event_calendar_agent.event_calendar_agent(),
        pattern_agent.pattern_agent(df),
        agents.risk_manager(df, capital, risk_pct),
        agents.expert_scout(news_before),
    ]
    ema200_val = float(df.iloc[-1]["ema200"])
    trend = 1 if float(df.iloc[-1]["close"]) > ema200_val else -1
    dec = council.chairman_decision(reports, levels, atr, last, trend_bias=trend, ema200=ema200_val)
    return dec, {"last_price": last, "atr": atr,
                 "rsi": float(df.iloc[-1]["rsi"]),
                 "ema200_trend": "صاعد" if df.iloc[-1]["close"] > df.iloc[-1]["ema200"] else "هابط"}


# ============================================================ حلقة الباك-تست
@dataclass
class Trade:
    day: pd.Timestamp
    decision: str
    score: float
    confidence: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    exit_price: float
    exit_window_days: int
    direction: int            # +1 شراء / -1 بيع / 0 انتظار
    pnl_pct: float
    hit_4d: bool              # تحركت مع القرار خلال 4 أيام؟
    mae: float                # أقصى حركة ضدك
    mfe: float                # أقصى حركة معك
    stop_hit: bool            # لمس وقف الخسارة خلال نافذة المتابعة


def run_replay(days_back: int = 180, step_days: int = 5,
               windows_days=(1, 3, 7), capital=10000.0, risk_pct=1.0,
               news_csv: Optional[str] = None,
               news_only_recent: int = 30):
    full = fetch_historical_days(2)
    full = full.sort_values("time").reset_index(drop=True)

    end_idx = len(full) - max(windows_days) - 1
    if end_idx < 210:
        raise RuntimeError("عدد صفوف غير كافٍ")

    external_news = load_news_csv(news_csv) if news_csv else []

    trades: list[Trade] = []
    decision_dist = {"شراء قوي 🟢🟢": 0, "شراء 🟢": 0, "انتظار / محايد ⚪": 0,
                     "بيع 🔴": 0, "بيع قوي 🔴🔴": 0}

    i = 210
    while i < end_idx:
        window = full.iloc[: i + 1].copy()
        ctime = full.iloc[i]["time"]
        if external_news:
            cutoff = ctime.to_pydatetime().replace(tzinfo=timezone.utc)
            news = [n for n in external_news
                    if n["published"] and n["published"] <= cutoff]
            news = news[:news_only_recent]
        else:
            # بدون أخبار حقيقية: إنشاء نشرة "محايدة" لحماية look-ahead
            news = [{"title": "", "source": "—", "section": "—", "published": ctime}]

        dec, ctx = simulate_decision(window, news, capital, risk_pct)
        if dec is None:
            i += step_days; continue

        direction = 1 if "شراء" in dec["decision"] else (-1 if "بيع" in dec["decision"] else 0)
        lv = dec["levels"]

        # متابعة الحركة بعد القرار
        exit_price, exit_w, mae, mfe, stop_hit = full.iloc[i]["close"], 0, 0.0, 0.0, False
        for w in windows_days:
            if i + w >= len(full):
                break
            fwd = full.iloc[i + 1: i + 1 + w]
            highs = fwd["high"].to_numpy()
            lows = fwd["low"].to_numpy()
            if direction == 1:
                if lv["entry"]:
                    pct_lows = (lows - lv["entry"]) / lv["entry"] * 100
                    pct_highs = (highs - lv["entry"]) / lv["entry"] * 100
                    mae = max(mae, float(pct_lows.min()))
                    mfe = max(mfe, float(pct_highs.max()))
                if lv.get("sl") and (lows <= lv["sl"]).any():
                    stop_hit = True; exit_w = w; exit_price = float(lv["sl"]); break
                if lv.get("tp1") and (highs >= lv["tp1"]).any():
                    pos = int((highs >= lv["tp1"]).argmax())
                    exit_w = w; exit_price = float(highs[pos]); break
            elif direction == -1 and lv["entry"]:
                pct_highs = (highs - lv["entry"]) / lv["entry"] * 100
                pct_lows = (lows - lv["entry"]) / lv["entry"] * 100
                mae = max(mae, float(pct_highs.max()))
                mfe = max(mfe, float(pct_lows.min()))
                if lv.get("sl") and (highs >= lv["sl"]).any():
                    stop_hit = True; exit_w = w; exit_price = float(lv["sl"]); break
                if lv.get("tp1") and (lows <= lv["tp1"]).any():
                    pos = int((lows <= lv["tp1"]).argmax())
                    exit_w = w; exit_price = float(lows[pos]); break

        if direction != 0 and lv["entry"]:
            pnl = direction * (exit_price - lv["entry"]) / lv["entry"] * 100
            hit_4d = (direction == 1 and exit_price > lv["entry"]) or \
                     (direction == -1 and exit_price < lv["entry"])
        else:
            pnl, hit_4d = 0.0, False

        decision_dist[dec["decision"]] = decision_dist.get(dec["decision"], 0) + 1
        trades.append(Trade(day=ctime, decision=dec["decision"],
                             score=dec["final_score"], confidence=dec["confidence"],
                             entry=(lv["entry"] or 0), sl=(lv["sl"] or 0),
                             tp1=(lv["tp1"] or 0), tp2=(lv["tp2"] or 0),
                             exit_price=exit_price, exit_window_days=exit_w,
                             direction=direction, pnl_pct=pnl, hit_4d=hit_4d,
                             mae=mae, mfe=mfe, stop_hit=stop_hit))
        i += step_days

    return _summarize(trades, decision_dist)


def _summarize(trades, decision_dist):
    n = len(trades)
    if n == 0:
        return {"error": "لم يُسجّل أي قرار بنوافذ بيانات كافية"}

    actionable = [t for t in trades if t.direction != 0]
    n_act = len(actionable)
    wins = [t for t in actionable if t.pnl_pct > 0]
    losses = [t for t in actionable if t.pnl_pct <= 0]
    stops_hit = [t for t in actionable if t.stop_hit]

    avg_pnl = sum(t.pnl_pct for t in actionable) / n_act if n_act else 0
    avg_pnl_w = sum(t.pnl_pct for t in wins) / len(wins) if wins else 0
    avg_pnl_l = sum(t.pnl_pct for t in losses) / len(losses) if losses else 0
    hit_4d_pct = 100 * sum(t.hit_4d for t in actionable) / n_act if n_act else 0
    win_rate = 100 * len(wins) / n_act if n_act else 0
    stop_rate = 100 * len(stops_hit) / n_act if n_act else 0

    # Equity curve بترتيب زمني: 1% رأس مال في كل صفقة (تركيب)
    equity = 10000.0
    eq_curve, sorted_trades = [], sorted(trades, key=lambda t: t.day)
    for t in sorted_trades:
        if t.direction != 0:
            equity *= (1 + t.pnl_pct / 100 * 0.50)
        eq_curve.append({"day": t.day.strftime("%Y-%m-%d"),
                         "equity": round(equity, 2),
                         "decision": t.decision, "pnl_pct": round(t.pnl_pct, 2)})

    best = max(actionable, key=lambda t: t.pnl_pct) if actionable else None
    worst = min(actionable, key=lambda t: t.pnl_pct) if actionable else None

    return {
        "summary": {
            "total_decisions": n,
            "actionable_decisions": n_act,
            "wait_decisions": n - n_act,
            "win_rate_pct": round(win_rate, 1),
            "direction_hit_4d_pct": round(hit_4d_pct, 1),
            "stop_loss_hit_pct": round(stop_rate, 1),
            "avg_pnl_per_trade_pct": round(avg_pnl, 3),
            "avg_winner_pct": round(avg_pnl_w, 3),
            "avg_loser_pct": round(avg_pnl_l, 3),
            "profit_factor": round((sum(t.pnl_pct for t in wins) /
                                    abs(sum(t.pnl_pct for t in losses))) if losses else float("inf"), 2),
            "final_equity_estimate": round(equity, 2),
            "decision_distribution": decision_dist,
        },
        "best_trade": _trade_to_dict(best) if best else None,
        "worst_trade": _trade_to_dict(worst) if worst else None,
        "last_decisions": [_trade_to_dict(t) for t in sorted_trades[-10:]],
        "equity_curve": eq_curve,
    }


def _trade_to_dict(t):
    if not t: return None
    return {"day": t.day.strftime("%Y-%m-%d"), "decision": t.decision,
            "score": t.score, "confidence": t.confidence,
            "entry": round(t.entry, 1), "sl": round(t.sl, 1),
            "tp1": round(t.tp1, 1), "tp2": round(t.tp2, 1),
            "exit_price": round(t.exit_price, 1),
            "exit_window_days": t.exit_window_days,
            "pnl_pct": round(t.pnl_pct, 3), "hit_4d": t.hit_4d,
            "mae_pct": round(t.mae, 3), "mfe_pct": round(t.mfe, 3),
            "stop_hit": t.stop_hit}


# ============================================================== CLI
def main():
    ap = argparse.ArgumentParser(description="باك-تست مجلس الذهب — قياس دقة التوصيات")
    ap.add_argument("--replay", action="store_true", help="تشغيل محاكاة تاريخية فعلية")
    ap.add_argument("--days", type=int, default=180, help="عدد الأيام للاختبار")
    ap.add_argument("--step", type=int, default=5, help="فاصل اجتماعات (يوم)")
    ap.add_argument("--capital", type=float, default=10000)
    ap.add_argument("--risk", type=float, default=1.0, help="نسبة المخاطرة %")
    ap.add_argument("--news-csv", type=str, default=None,
                    help="ملف CSV للأخبار التاريخية بصيغة: time,title,source,section")
    ap.add_argument("--out", type=str, default="backtest_report.json")
    args = ap.parse_args()

    if not args.replay:
        ap.print_help(); return

    print(f"⏳ تشغيل باك-تست: {args.days} يوم، فاصل كل {args.step} أيام")
    print(f"💰 رأس مال {args.capital:,.0f}$ | مخاطرة {args.risk}% | "
          f"أخبار تاريخية: {'من ملف' if args.news_csv else 'محايدة (لا look-ahead)'}")
    start = datetime.now()
    res = run_replay(days_back=args.days, step_days=args.step,
                     capital=args.capital, risk_pct=args.risk, news_csv=args.news_csv)
    elapsed = (datetime.now() - start).total_seconds()

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=str)

    if "summary" in res:
        s = res["summary"]
        print("\n" + "=" * 60)
        print("📊  ملخص الباك-تست")
        print("=" * 60)
        print(f"إجمالي القرارات: {s['total_decisions']} (قابلة للتنفيذ: {s['actionable_decisions']})")
        print(f"نسبة الفوز: {s['win_rate_pct']}%")
        print(f"متوسط ربح لكل صفقة: {s['avg_pnl_per_trade_pct']}%")
        print(f"متوسط الرابح: {s['avg_winner_pct']}% | الخاسر: {s['avg_loser_pct']}%")
        print(f"معامل الربح: {s['profit_factor']}")
        print(f"نسبة تفعيل وقف الخسارة: {s['stop_loss_hit_pct']}%")
        print(f"التوزيع: {s['decision_distribution']}")
        if res.get("best_trade"):
            b = res["best_trade"]
            print(f"\n🏆 أفضل قرار: {b['day']} {b['decision']} "
                  f"ربح {b['pnl_pct']:+.2f}% (دخول {b['entry']}$, خرج يوم {b['exit_window_days']})")
        if res.get("worst_trade"):
            w = res["worst_trade"]
            print(f"💔 أصعب قرار: {w['day']} {w['decision']} "
                  f"خسارة {w['pnl_pct']:+.2f}% (دخول {w['entry']}$)")
        print(f"\n⏱️  زمن التشغيل: {elapsed:.1f}s")
        print(f"📄 تقرير JSON: {args.out}")
    else:
        print("❌", res)


if __name__ == "__main__":
    main()

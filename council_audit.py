import argparse
import json
from collections import Counter
from datetime import timedelta, timezone

import pandas as pd

import backtester_v5


def run(prices_csv, news_csv, macro_csv, step=5):
    prices = backtester_v5.load_prices_csv(prices_csv)
    news = backtester_v5.load_news_csv(news_csv)
    macro = pd.read_csv(macro_csv)
    rows, reasons = [], Counter()
    for i in range(210, len(prices) - 8, step):
        history = prices.iloc[:i + 1].copy()
        as_of = pd.Timestamp(prices.iloc[i]["time"])
        as_of = as_of.tz_localize("UTC") if as_of.tzinfo is None else as_of.tz_convert("UTC")
        window_start = as_of - pd.Timedelta(hours=72)
        selected = [n for n in news if n["published"] and
                    window_start.to_pydatetime() <= n["published"] <= as_of.to_pydatetime()]
        dec, _ = backtester_v5.simulate_decision(
            history, selected, as_of=as_of.to_pydatetime(), macro_history=macro)
        reason = dec.get("vetoed") or "passed"
        if reason.startswith("فلتر الجودة"):
            reason_key = "quality"
        elif reason.startswith("بوابة أحداث"):
            reason_key = "event"
        elif "انقسام" in reason:
            reason_key = "split"
        else:
            reason_key = "passed"
        reasons[reason_key] += 1
        rows.append({"day": str(as_of), "score": dec["final_score"],
                     "signal": dec["signal"], "reason": reason_key})
    frame = pd.DataFrame(rows)
    return {
        "decisions": len(frame), "signals": int((frame.signal != 0).sum()),
        "score_min": round(float(frame.score.min()), 2),
        "score_max": round(float(frame.score.max()), 2),
        "score_abs_p90": round(float(frame.score.abs().quantile(0.9)), 2),
        "block_reasons": dict(reasons),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--news", default="gold_news_master.csv")
    parser.add_argument("--macro", default="data_cache/macro_point_in_time.csv")
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--out", default="data_cache/council_audit.json")
    args = parser.parse_args()
    report = run(args.prices, args.news, args.macro, args.step)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""اختبار إزالة وكيل واحد مع تقسيم زمني ثابت، بلا ضبط على المستقبل."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import backtester_v5
import council


PERIODS = {
    "discovery_2008_2018": ("2008-01-01", "2018-12-31"),
    "validation_2019_2022": ("2019-01-01", "2022-12-31"),
    "holdout_2023_2026": ("2023-01-01", "2026-12-31"),
}


def metrics(trades, start, end):
    start_at = pd.Timestamp(start, tz="UTC")
    end_at = pd.Timestamp(end, tz="UTC")
    def in_period(trade):
        day = pd.Timestamp(trade.day)
        day = day.tz_localize("UTC") if day.tzinfo is None else day.tz_convert("UTC")
        return start_at <= day <= end_at
    selected = [t for t in trades if in_period(t)]
    wins = [t.pnl_pct for t in selected if t.pnl_pct > 0]
    losses = [t.pnl_pct for t in selected if t.pnl_pct <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {
        "trades": len(selected),
        "win_rate_pct": round(100 * len(wins) / len(selected), 1) if selected else None,
        "sum_pnl_pct": round(sum(t.pnl_pct for t in selected), 3),
        "profit_factor": round(gross_win / gross_loss, 3) if gross_loss else None,
        "stop_rate_pct": round(100 * sum(t.stop_hit for t in selected) / len(selected), 1)
                         if selected else None,
    }


def run(args):
    original = dict(council.WEIGHTS_V2)
    variants = {"full_council": None}
    variants.update({f"without_{key}": key for key, weight in original.items()
                     if weight > 0 and key not in {"macro", "expert"}})
    report = {"method": "one-agent-out; fixed chronological periods", "variants": {}}
    try:
        for name, removed in variants.items():
            council.WEIGHTS_V2.clear()
            council.WEIGHTS_V2.update(original)
            if removed:
                council.WEIGHTS_V2[removed] = 0.0
            _, trades, _ = backtester_v5.run_replay(
                step_days=args.step, prices_csv=args.prices, macro_csv=args.macro,
                events_csv=args.events, news_csv=args.news)
            report["variants"][name] = {
                "removed": removed,
                "all": metrics(trades, "2008-01-01", "2026-12-31"),
                **{period: metrics(trades, start, end)
                   for period, (start, end) in PERIODS.items()},
            }
            print(name, report["variants"][name]["all"], flush=True)
    finally:
        council.WEIGHTS_V2.clear()
        council.WEIGHTS_V2.update(original)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", required=True)
    parser.add_argument("--macro", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--news", default=None)
    parser.add_argument("--step", type=int, default=10)
    parser.add_argument("--out", default="data_cache/agent_ablation_2008_2026.json")
    args = parser.parse_args()
    report = run(args)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved -> {args.out}")


if __name__ == "__main__":
    main()

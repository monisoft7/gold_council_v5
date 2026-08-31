# -*- coding: utf-8 -*-
"""تدقيق استقلال الوكلاء قبل أي تعديل أوزان أو ablation تداولي."""
from __future__ import annotations

import argparse
import json

import pandas as pd

import indicators
import agents
import macro_regime_agent
import cot_agent
import seasonality_agent
import pattern_agent
import cross_asset_agent


def run(prices_csv, macro_csv, step=5):
    prices = pd.read_csv(prices_csv)
    prices["time"] = pd.to_datetime(prices["time"], utc=True)
    macro = pd.read_csv(macro_csv)
    rows = []
    for i in range(210, len(prices) - 8, step):
        history = indicators.add_all(prices.iloc[:i + 1].copy())
        as_of = prices.iloc[i]["time"]
        reports = [
            agents.technical_analyst(history),
            macro_regime_agent.macro_regime_agent(macro, as_of),
            cot_agent.cot_positioning_agent(macro, as_of),
            seasonality_agent.seasonality_agent(history, ref_date=as_of.to_pydatetime()),
            pattern_agent.pattern_agent(history),
            cross_asset_agent.cross_asset_from_history(
                history[["time", "close"]], macro, as_of),
        ]
        row = {"day": str(as_of)}
        row.update({r.key: r.score for r in reports})
        rows.append(row)
    scores = pd.DataFrame(rows)
    keys = [c for c in scores.columns if c != "day"]
    summary = {}
    for key in keys:
        s = pd.to_numeric(scores[key], errors="coerce").fillna(0)
        summary[key] = {
            "mean": round(float(s.mean()), 2), "std": round(float(s.std()), 2),
            "bull_votes": int((s > 10).sum()), "bear_votes": int((s < -10).sum()),
            "neutral": int((s.abs() <= 10).sum()),
            "strong": int((s.abs() >= 30).sum()),
        }
    corr = scores[keys].corr().round(3).fillna(0).to_dict()
    return {"rows": len(scores), "agents": summary, "score_correlation": corr}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="gold_3y_daily.csv")
    parser.add_argument("--macro", default="data_cache/macro_point_in_time.csv")
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--out", default="data_cache/agent_audit.json")
    args = parser.parse_args()
    report = run(args.prices, args.macro, args.step)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

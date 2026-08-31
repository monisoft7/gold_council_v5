# -*- coding: utf-8 -*-
"""يبني لقطة ماكرو يومية point-in-time من الكاش الرسمي فقط."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from point_in_time import asof_join, assert_no_future


TOLERANCE = {
    "real_yield_10y": "7D", "nominal_yield_10y": "7D",
    "broad_dollar": "7D", "vix": "7D",
    "cpi": "62D", "payrolls": "62D", "unemployment": "62D",
    "fed_funds": "62D",
}


def build(decisions: pd.DataFrame, official_dir) -> pd.DataFrame:
    out = decisions.copy()
    out["decision_at"] = pd.to_datetime(out["decision_at"], utc=True)
    base = Path(official_dir)
    for feature, tolerance in TOLERANCE.items():
        path = base / f"fred_{feature}.csv"
        if not path.exists():
            continue
        facts = pd.read_csv(path)
        out = asof_join(out, facts, ["value"], tolerance=tolerance,
                        prefix=f"{feature}_")
    cot_path = base / "cftc_gold_cot.csv"
    if cot_path.exists():
        cot = pd.read_csv(cot_path)
        cot_values = ["open_interest", "noncommercial_long", "noncommercial_short",
                      "noncommercial_net", "commercial_net"]
        cot_values = [c for c in cot_values if c in cot.columns]
        out = asof_join(out, cot, cot_values, tolerance="10D", prefix="cot_")
    assert_no_future(out)
    # أسماء يستهلكها وكيل الأصول، مع إبقاء الأسماء الرسمية الأصلية.
    out["dxy"] = out.get("broad_dollar_value")
    out["us10y"] = out.get("real_yield_10y_value")
    out["vix"] = out.get("vix_value")
    out["available_at"] = out["decision_at"]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prices", default="data_cache/gold_daily_2008_2026.csv")
    parser.add_argument("--official-dir", default="data_cache/official")
    parser.add_argument("--out", default="data_cache/macro_point_in_time.csv")
    args = parser.parse_args()
    prices = pd.read_csv(args.prices)
    decisions = pd.DataFrame({"decision_at": prices["time"]})
    store = build(decisions, args.official_dir)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    store.to_csv(args.out, index=False, encoding="utf-8")
    coverage = {c: round(float(store[c].notna().mean()), 3)
                for c in store.columns if c.endswith("_value")}
    print(f"saved {len(store)} snapshots -> {args.out}")
    print("coverage", coverage)


if __name__ == "__main__":
    main()

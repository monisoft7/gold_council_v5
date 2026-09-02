# -*- coding: utf-8 -*-
"""Objective promotion gate for automatic MT5 DEMO order submission.

The gate consumes reports produced by ``council_intraday_replay.py``. It does
not optimize weights or thresholds; it only checks whether the unchanged
strategy survived discovery, holdout, and a later forward period under the
same execution rules used by the MT5 bridge.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "data_cache" / "strategy_promotion_report.json"
THRESHOLDS = {
    "minimum_discovery_trades": 40,
    "minimum_holdout_trades": 20,
    "minimum_forward_trades": 20,
    "minimum_discovery_profit_factor": 1.05,
    "minimum_holdout_profit_factor": 1.20,
    "minimum_forward_profit_factor": 1.25,
    "minimum_forward_signal_months": 6,
    "maximum_10_day_signal_concentration": 0.35,
}


def _execution_metric(report: dict) -> dict:
    metric = report.get("execution_240m")
    return metric if isinstance(metric, dict) else {}


def _signal_diversity(decisions: pd.DataFrame | None) -> dict:
    if decisions is None or decisions.empty or "decision_time" not in decisions:
        return {"signal_months": 0, "max_10_day_concentration": 1.0, "signals": 0}
    if "execution_net_240m_pct" in decisions:
        active = pd.to_numeric(decisions["execution_net_240m_pct"], errors="coerce").notna()
    else:
        active = pd.to_numeric(decisions.get("signal"), errors="coerce").fillna(0).ne(0)
    times = pd.to_datetime(decisions.loc[active, "decision_time"], errors="coerce", utc=True)
    times = times.dropna().sort_values()
    if times.empty:
        return {"signal_months": 0, "max_10_day_concentration": 1.0, "signals": 0}
    months = int(times.dt.tz_localize(None).dt.to_period("M").nunique())
    max_cluster = max(
        int(((times >= start) & (times < start + pd.Timedelta(days=10))).sum())
        for start in times
    )
    return {
        "signal_months": months,
        "max_10_day_concentration": round(max_cluster / len(times), 4),
        "signals": int(len(times)),
    }


def evaluate_promotion(discovery: dict, holdout: dict, forward: dict,
                       forward_decisions: pd.DataFrame | None = None) -> dict:
    reports = {"discovery": discovery, "holdout": holdout, "forward": forward}
    metrics = {name: _execution_metric(report) for name, report in reports.items()}
    diversity = _signal_diversity(forward_decisions)

    checks = {
        "same_intraday_4h_profile": all(
            report.get("strategy_profile") == "intraday_4h" for report in reports.values()
        ),
        "observed_spread_in_all_periods": all(
            bool((report.get("cost_model") or {}).get("observed_mt5_spread"))
            for report in reports.values()
        ),
        "live_execution_metric_in_all_periods": all(bool(metric) for metric in metrics.values()),
        "discovery_sample": int(metrics["discovery"].get("trades", 0))
        >= THRESHOLDS["minimum_discovery_trades"],
        "holdout_sample": int(metrics["holdout"].get("trades", 0))
        >= THRESHOLDS["minimum_holdout_trades"],
        "forward_sample": int(metrics["forward"].get("trades", 0))
        >= THRESHOLDS["minimum_forward_trades"],
        "discovery_profit_factor": float(metrics["discovery"].get("profit_factor") or 0)
        >= THRESHOLDS["minimum_discovery_profit_factor"],
        "holdout_profit_factor": float(metrics["holdout"].get("profit_factor") or 0)
        >= THRESHOLDS["minimum_holdout_profit_factor"],
        "forward_profit_factor": float(metrics["forward"].get("profit_factor") or 0)
        >= THRESHOLDS["minimum_forward_profit_factor"],
        "positive_mean_return_each_period": all(
            float(metric.get("mean_net_return_pct") or 0) > 0 for metric in metrics.values()
        ),
        "forward_signal_month_diversity": diversity["signal_months"]
        >= THRESHOLDS["minimum_forward_signal_months"],
        "forward_cluster_concentration": diversity["max_10_day_concentration"]
        <= THRESHOLDS["maximum_10_day_signal_concentration"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "promotion_allowed": not failed,
        "strategy_profile": "intraday_4h",
        "metric": "live TP1/SL/4h execution after spread and slippage",
        "thresholds": THRESHOLDS,
        "observed": {**metrics, "forward_diversity": diversity},
        "checks": checks,
        "failed_checks": failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--forward", required=True)
    parser.add_argument("--forward-decisions", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in (
        args.discovery, args.holdout, args.forward
    )]
    decisions = pd.read_csv(args.forward_decisions, low_memory=False)
    result = evaluate_promotion(*reports, forward_decisions=decisions)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

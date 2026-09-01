# -*- coding: utf-8 -*-
"""تدقيق اتجاه وكيل المفاجأة الرقمية على شموع MT5 بعد الإصدار."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from mt5_event_history import event_return_summary


HORIZONS = (15, 60, 240, 1440)


def _profit_factor(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    gains = clean[clean > 0].sum()
    losses = -clean[clean < 0].sum()
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return float(gains / losses)


def _wilson_interval(wins: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    if total <= 0:
        return None
    p = wins / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _metrics(values: pd.Series) -> dict:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    wins = int((clean > 0).sum())
    interval = _wilson_interval(wins, len(clean))
    factor = _profit_factor(clean) if len(clean) else None
    return {
        "n": len(clean),
        "accuracy_pct": round(wins / len(clean) * 100, 2) if len(clean) else None,
        "wilson_95_low_pct": round(interval[0] * 100, 2) if interval else None,
        "wilson_95_high_pct": round(interval[1] * 100, 2) if interval else None,
        "mean_directed_return_pct": round(float(clean.mean()), 4) if len(clean) else None,
        "median_directed_return_pct": round(float(clean.median()), 4) if len(clean) else None,
        "profit_factor": None if factor is None else (
            "inf" if factor == float("inf") else round(float(factor), 4)
        ),
    }


def build_event_returns(bars: pd.DataFrame, *, timeframe_minutes=5,
                        point=0.01) -> pd.DataFrame:
    frame = bars.copy()
    frame["event_time"] = pd.to_datetime(frame["event_time"], errors="coerce", utc=True)
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    rows = []
    for (event_time, event_type), window in frame.groupby(["event_time", "event_type"]):
        rows.append({"event_time": event_time, "event_type": event_type,
                     **event_return_summary(window, timeframe_minutes=timeframe_minutes,
                                            point=point, horizons_minutes=HORIZONS)})
    return pd.DataFrame(rows)


def aggregate_surprises(surprises: pd.DataFrame) -> pd.DataFrame:
    frame = surprises.copy()
    frame["event_time"] = pd.to_datetime(frame["release_time"], errors="coerce", utc=True)
    frame["gold_score"] = pd.to_numeric(frame["gold_score"], errors="coerce")
    grouped = frame.groupby(["event_time", "event_type"], as_index=False).agg(
        gold_score=("gold_score", "mean"),
        component_count=("title", "size"),
        source=("source", "first"),
        availability_assumption=("availability_assumption", "first"),
    )
    grouped["signal"] = grouped["gold_score"].apply(
        lambda value: 1 if value > 10 else -1 if value < -10 else 0
    )
    return grouped


def evaluate(surprises: pd.DataFrame, event_returns: pd.DataFrame, *,
             split_date="2023-01-01") -> tuple[pd.DataFrame, dict]:
    signals = aggregate_surprises(surprises)
    merged = signals.merge(event_returns, on=["event_time", "event_type"], how="left")
    report = {
        "research_only": True,
        "promotion_allowed": False,
        "minimum_directional_events_for_promotion": 30,
        "availability_limitation": "historical actual capture timestamp unavailable",
        "events": len(merged), "directional_events": int((merged["signal"] != 0).sum()),
        "by_horizon": {}, "by_event_type": {},
    }
    directional = merged[merged["signal"] != 0].copy()
    for horizon in HORIZONS:
        raw_col = f"return_{horizon}m_pct"
        directed_col = f"directed_{horizon}m_pct"
        directional[directed_col] = directional["signal"] * pd.to_numeric(
            directional[raw_col], errors="coerce"
        )
        report["by_horizon"][str(horizon)] = _metrics(directional[directed_col])
    for event_type, group in directional.groupby("event_type"):
        report["by_event_type"][event_type] = {
            str(h): _metrics(group[f"directed_{h}m_pct"]) for h in HORIZONS
        }
    split_at = pd.Timestamp(split_date, tz="UTC")
    discovery = directional[directional["event_time"] < split_at]
    validation = directional[directional["event_time"] >= split_at]
    report["temporal_split"] = {
        "split_date": split_at.isoformat(),
        "discovery": {str(h): _metrics(discovery[f"directed_{h}m_pct"])
                      for h in HORIZONS},
        "validation": {str(h): _metrics(validation[f"directed_{h}m_pct"])
                       for h in HORIZONS},
    }
    eligible = {
        h: _profit_factor(discovery[f"directed_{h}m_pct"].dropna())
        for h in HORIZONS
        if discovery[f"directed_{h}m_pct"].notna().sum() >= 30
    }
    selected = max(eligible, key=lambda h: eligible[h] or 0.0) if eligible else None
    report["discovery_selected_horizon_minutes"] = selected
    if selected is not None:
        validation_values = validation[f"directed_{selected}m_pct"].dropna()
        report["selected_horizon_cost_stress"] = {
            str(cost): _metrics(validation_values - cost)
            for cost in (0.02, 0.05, 0.10, 0.20)
        }
        report["selected_horizon_yearly"] = {
            str(year): _metrics(group[f"directed_{selected}m_pct"])
            for year, group in directional.groupby(directional["event_time"].dt.year)
        }
    return directional, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surprises", default="data_cache/economic_surprises_2025.csv")
    parser.add_argument("--bars", default="data_cache/mt5_event_bars_2025_2026.csv")
    parser.add_argument("--output", default="data_cache/numeric_surprise_audit.csv")
    parser.add_argument("--report", default="data_cache/numeric_surprise_audit.json")
    parser.add_argument("--point", type=float, default=0.01)
    parser.add_argument("--timeframe-minutes", type=int, default=5)
    parser.add_argument("--split-date", default="2023-01-01")
    args = parser.parse_args()
    returns = build_event_returns(pd.read_csv(args.bars),
                                  timeframe_minutes=args.timeframe_minutes,
                                  point=args.point)
    rows, report = evaluate(pd.read_csv(args.surprises), returns,
                            split_date=args.split_date)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(args.output, index=False, encoding="utf-8")
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

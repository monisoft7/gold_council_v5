# -*- coding: utf-8 -*-
"""بوابة قبول صارمة لأي CSV خارجي يدّعي أنه مجموعة NFP/ذهب."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from mt5_event_history import canonicalize_events


SURPRISE_INPUTS = ("nfp_actual", "nfp_forecast", "nfp_surprise")
OUTCOME_COLUMNS = ("xau_m5_range_pips", "xau_h1_direction")
PROVENANCE_COLUMNS = ("source", "feature_available_at")


def _resolve_timestamps(raw_dates: pd.Series, source_timezone: str | None) -> pd.Series:
    """Parse explicit offsets, or localize deliberately declared naive timestamps."""
    resolved = []
    zone = ZoneInfo(source_timezone) if source_timezone else None
    for raw in raw_dates:
        try:
            stamp = pd.Timestamp(raw)
            if stamp.tzinfo is None:
                if zone is None:
                    resolved.append(pd.NaT)
                    continue
                stamp = stamp.tz_localize(zone, ambiguous="raise", nonexistent="raise")
            resolved.append(stamp.tz_convert("UTC"))
        except (TypeError, ValueError):
            resolved.append(pd.NaT)
    return pd.Series(resolved, index=raw_dates.index, dtype="datetime64[ns, UTC]")


def audit_nfp_dataset(frame: pd.DataFrame, *, as_of=None,
                      official_events: pd.DataFrame | None = None,
                      source_timezone: str | None = None) -> dict:
    data = frame.copy()
    current = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    raw_dates = data.get("date", pd.Series(index=data.index, dtype=object)).astype(str)
    timestamps = _resolve_timestamps(raw_dates, source_timezone)
    valid_dates = timestamps.notna()
    timezone_explicit = raw_dates.str.contains(
        r"(?:Z|[+-]\d{2}:?\d{2})$", flags=re.IGNORECASE, regex=True
    )
    available_inputs = [column for column in SURPRISE_INPUTS if column in data]
    if len(available_inputs) == len(SURPRISE_INPUTS) and len(data):
        numeric_complete = float(data[list(SURPRISE_INPUTS)].notna().all(axis=1).mean())
    else:
        numeric_complete = 0.0
    if all(column in data for column in SURPRISE_INPUTS) and len(data):
        numeric = data[list(SURPRISE_INPUTS)].apply(pd.to_numeric, errors="coerce")
        surprise_consistent = (
            (numeric["nfp_actual"] - numeric["nfp_forecast"] - numeric["nfp_surprise"])
            .abs().le(0.001)
        )
        surprise_consistency = float(surprise_consistent.mean())
    else:
        surprise_consistency = 0.0
    future = timestamps > current
    future_outcome_rows = 0
    for column in OUTCOME_COLUMNS:
        if column in data:
            future_outcome_rows += int((future & data[column].notna()).sum())
    schedule_rate = None
    matched_dates = None
    maximum_schedule_delta_minutes = None
    mismatched_timestamps = []
    if official_events is not None and not official_events.empty and valid_dates.any():
        reference = official_events.copy()
        if "source" in reference:
            trusted = reference["source"].astype(str).str.contains(
                "FRED/ALFRED+BLS", case=False, regex=False
            )
            if trusted.any():
                reference = reference[trusted]
        official = canonicalize_events(reference)
        official_times = official.loc[official["event_type"] == "NFP", "event_time"]
        comparable = timestamps[valid_dates & ~future]
        if len(comparable):
            deltas = comparable.apply(
                lambda stamp: min((official_times - stamp).abs()).total_seconds() / 60
                if len(official_times) else float("inf")
            ).astype(float)
            matched_dates = int((deltas <= 5).sum())
            mismatched_timestamps = [
                stamp.isoformat() for stamp in comparable[deltas > 5]
            ]
            schedule_rate = matched_dates / len(comparable)
            maximum_schedule_delta_minutes = round(float(deltas.max()), 2)
    timezone_resolved = timezone_explicit | (valid_dates if source_timezone else False)
    provenance_present = all(column in data for column in PROVENANCE_COLUMNS)
    checks = {
        "has_rows": len(data) > 0,
        "valid_timestamp_rate_at_least_95pct": float(valid_dates.mean()) >= 0.95 if len(data) else False,
        "timezone_resolved_rate_at_least_95pct": float(timezone_resolved.mean()) >= 0.95 if len(data) else False,
        "nfp_numeric_inputs_complete_at_least_95pct": numeric_complete >= 0.95,
        "surprise_arithmetic_consistent_100pct": surprise_consistency == 1.0,
        "no_future_price_outcomes": future_outcome_rows == 0,
        "official_schedule_match_100pct": schedule_rate == 1.0,
    }
    structurally_valid = all(checks.values())
    reasons = [name for name, passed in checks.items() if not passed]
    if not provenance_present:
        reasons.append("point_in_time_provenance_columns_present")
    return {
        "rows": len(data),
        "start": timestamps.min().isoformat() if valid_dates.any() else None,
        "end": timestamps.max().isoformat() if valid_dates.any() else None,
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "numeric_input_complete_pct": round(numeric_complete * 100, 2),
        "surprise_arithmetic_consistency_pct": round(surprise_consistency * 100, 2),
        "explicit_timezone_pct": round(float(timezone_explicit.mean() * 100), 2)
        if len(data) else 0.0,
        "resolved_timezone_pct": round(float(timezone_resolved.mean() * 100), 2)
        if len(data) else 0.0,
        "source_timezone": source_timezone,
        "future_rows": int(future.sum()),
        "future_outcome_cells": future_outcome_rows,
        "official_schedule_matched_rows": matched_dates,
        "official_schedule_match_pct": round(schedule_rate * 100, 2)
        if schedule_rate is not None else None,
        "maximum_schedule_delta_minutes": maximum_schedule_delta_minutes,
        "mismatched_timestamps": mismatched_timestamps,
        "point_in_time_provenance_columns_present": provenance_present,
        "checks": checks,
        "structurally_valid": structurally_valid,
        "usable_for_surprise_model": structurally_valid and provenance_present,
        "usable_for_point_in_time_shadow_features": structurally_valid and provenance_present,
        "rejection_reasons": reasons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--official-events", default="data_cache/events_2008_2026.csv")
    parser.add_argument("--as-of")
    parser.add_argument(
        "--source-timezone",
        help="IANA timezone for naive date values, for example Asia/Jerusalem",
    )
    parser.add_argument("--report", default="data_cache/nfp_external_dataset_quality.json")
    args = parser.parse_args()
    data = pd.read_csv(args.input, low_memory=False)
    official = pd.read_csv(args.official_events) if Path(args.official_events).exists() else None
    report = audit_nfp_dataset(
        data, as_of=args.as_of, official_events=official,
        source_timezone=args.source_timezone,
    )
    target = Path(args.report); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

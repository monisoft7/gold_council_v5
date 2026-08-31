# -*- coding: utf-8 -*-
"""أدوات موحدة تمنع تسرب المستقبل في البيانات التاريخية.

كل سجل خارجي يجب أن يحمل:
  observed_at  وقت القياس الاقتصادي/السوقي
  released_at  وقت نشره من المصدر
  available_at أول وقت كان يمكن للنظام معرفته فعلاً

الدمج التاريخي يتم دائماً على available_at وباتجاه backward فقط.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

import pandas as pd


TIME_COLUMNS = ("observed_at", "released_at", "available_at")


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def normalize_records(df: pd.DataFrame, *, observed_col: str,
                      released_col: str | None = None,
                      available_col: str | None = None,
                      source: str = "unknown") -> pd.DataFrame:
    """يحوّل أي مصدر إلى عقد point-in-time موحد مع تحقق صارم."""
    out = df.copy()
    out["observed_at"] = _utc(out[observed_col])
    out["released_at"] = (_utc(out[released_col]) if released_col
                          else out["observed_at"])
    out["available_at"] = (_utc(out[available_col]) if available_col
                           else out["released_at"])
    out["source_id"] = out.get("source_id", source)
    out = out.dropna(subset=list(TIME_COLUMNS))
    invalid = ((out["released_at"] < out["observed_at"]) |
               (out["available_at"] < out["released_at"]))
    if invalid.any():
        raise ValueError("point-in-time contract violated: observed <= released <= available")
    return out.sort_values("available_at").reset_index(drop=True)


def asof_join(decisions: pd.DataFrame, facts: pd.DataFrame,
              value_cols: Iterable[str], *, decision_col: str = "decision_at",
              tolerance: str | pd.Timedelta | None = None,
              prefix: str = "") -> pd.DataFrame:
    """يلحق آخر حقيقة كانت متاحة لحظة القرار، ولا يسمح بالاتجاه المستقبلي."""
    left = decisions.copy()
    left[decision_col] = _utc(left[decision_col])
    right = facts.copy()
    right["available_at"] = _utc(right["available_at"])
    cols = ["available_at", *value_cols]
    right = right[cols].dropna(subset=["available_at"])
    rename = {c: f"{prefix}{c}" for c in value_cols}
    right = right.rename(columns=rename)
    available_name = f"{prefix}available_at" if prefix else "fact_available_at"
    right = right.rename(columns={"available_at": available_name})
    tol = pd.Timedelta(tolerance) if tolerance is not None else None
    merged = pd.merge_asof(
        left.sort_values(decision_col), right.sort_values(available_name),
        left_on=decision_col, right_on=available_name,
        direction="backward", tolerance=tol,
    )
    leaked = merged[available_name].notna() & (
        merged[available_name] > merged[decision_col])
    if leaked.any():
        raise AssertionError("future data leaked into historical snapshot")
    return merged


def news_window(news: pd.DataFrame, as_of, hours: int = 72) -> pd.DataFrame:
    """أخبار كانت متاحة فقط ضمن نافذة سابقة للقرار."""
    cutoff = pd.Timestamp(as_of)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    available = _utc(news["available_at"])
    start = cutoff - pd.Timedelta(hours=hours)
    return news.loc[(available >= start) & (available <= cutoff)].copy()


def assert_no_future(snapshot: pd.DataFrame, decision_col="decision_at") -> None:
    """حارس عام يستخدم في الاختبارات وقبل تدريب أي نموذج."""
    decision = _utc(snapshot[decision_col])
    for col in (c for c in snapshot.columns if c.endswith("available_at")):
        available = _utc(snapshot[col])
        if (available.notna() & (available > decision)).any():
            raise AssertionError(f"future leakage detected in {col}")

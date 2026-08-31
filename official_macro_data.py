# -*- coding: utf-8 -*-
"""موصلات المصادر الرسمية؛ لا منطق تداول داخل هذه الطبقة.

FRED/ALFRED هو مصدر الباكتيست المفضل لأنه يعيد تاريخ أول إتاحة للقيمة.
BLS يستخدم للتدقيق والقراءة الحية؛ استجابته لا تحمل دائماً وقت الإصدار،
ولذلك لا تُدخل بياناته التاريخية في الباكتيست بلا تقويم إصدار منفصل.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests

from env_loader import env
from point_in_time import normalize_records


FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
BLS_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

FRED_SERIES = {
    "real_yield_10y": "DFII10",
    "nominal_yield_10y": "DGS10",
    "broad_dollar": "DTWEXBGS",
    "vix": "VIXCLS",
    "cpi": "CPIAUCSL",
    "payrolls": "PAYEMS",
    "unemployment": "UNRATE",
    "fed_funds": "FEDFUNDS",
}
DAILY_MARKET_SERIES = {"DFII10", "DGS10", "DTWEXBGS", "VIXCLS"}

BLS_SERIES = {
    "cpi_all": "CUSR0000SA0",
    "core_cpi": "CUSR0000SA0L1E",
    "payrolls": "CES0000000001",
    "unemployment": "LNS14000000",
}


def fred_initial_release(series_id: str, start: str, end: str,
                         api_key: str | None = None, timeout=30) -> pd.DataFrame:
    """القيم الأولية فقط؛ revisions اللاحقة لا تعاد كتابتها فوق الماضي."""
    key = api_key or env.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("FRED_API_KEY is required")
    params = {
            "series_id": series_id, "api_key": key, "file_type": "json",
            "observation_start": start, "observation_end": end,
    }
    if series_id in DAILY_MARKET_SERIES:
        params["output_type"] = 1
    else:
        params.update({"realtime_start": "1776-07-04",
                       "realtime_end": "9999-12-31", "output_type": 4})
    try:
        response = requests.get(FRED_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        # requests يضم URL كاملاً (وفيه المفتاح) داخل نص الاستثناء.
        status = exc.response.status_code if exc.response is not None else "network"
        detail = ""
        if exc.response is not None:
            try:
                detail = str(exc.response.json().get("error_message", ""))
            except Exception:
                detail = ""
        detail = detail.replace(key, "<redacted>")[:300]
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(
            f"FRED request failed for series {series_id} (status={status}){suffix}") from None
    rows = []
    for item in response.json().get("observations", []):
        if item.get("value") in (None, "."):
            continue
        released = (item["date"] if series_id in DAILY_MARKET_SERIES
                    else item["realtime_start"])
        rows.append({
            "observed": item["date"], "released": released,
            "value": float(item["value"]), "series_id": series_id,
        })
    raw = pd.DataFrame(rows)
    if raw.empty:
        return pd.DataFrame(columns=["observed_at", "released_at", "available_at",
                                     "value", "series_id", "source_id"])
    # FRED يعطي تاريخاً بلا ساعة؛ اليوم التالي افتراض محافظ يمنع التداول
    # قبل معرفة توقيت الإصدار الفعلي.
    raw["available"] = pd.to_datetime(raw["released"], utc=True) + pd.Timedelta(days=1)
    return normalize_records(raw, observed_col="observed", released_col="released",
                             available_col="available", source="fred_alfred_initial")


def fred_bundle(start: str, end: str, api_key=None) -> pd.DataFrame:
    merged = None
    for name, series_id in FRED_SERIES.items():
        frame = fred_initial_release(series_id, start, end, api_key=api_key)
        part = frame[["observed_at", "released_at", "available_at", "value"]].rename(
            columns={"value": name})
        merged = part if merged is None else pd.merge(
            merged, part, on=["observed_at", "released_at", "available_at"], how="outer")
    return merged.sort_values("available_at").reset_index(drop=True)


def bls_series(series_ids, start_year: int, end_year: int,
               api_key: str | None = None, timeout=30) -> pd.DataFrame:
    """قراءة رسمية؛ الناتج موسوم unsafe_for_historical_backtest بوضوح."""
    key = api_key or env.get("BLS_API_KEY")
    payload = {"seriesid": list(series_ids), "startyear": str(start_year),
               "endyear": str(end_year), "catalog": True}
    if key:
        payload["registrationkey"] = key
    try:
        response = requests.post(BLS_URL, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        raise RuntimeError("BLS request failed") from None
    body = response.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError("BLS request failed: " + "; ".join(body.get("message", [])))
    fetched = datetime.now(timezone.utc)
    rows = []
    for series in body.get("Results", {}).get("series", []):
        for item in series.get("data", []):
            period = item.get("period", "")
            if not period.startswith("M") or period == "M13":
                continue
            try:
                value = float(item["value"])
            except (TypeError, ValueError):
                continue
            rows.append({
                "series_id": series["seriesID"],
                "observed_at": pd.Timestamp(int(item["year"]), int(period[1:]), 1, tz="UTC"),
                "value": value, "retrieved_at": fetched,
                "point_in_time_safe": False,
            })
    return pd.DataFrame(rows).sort_values(["series_id", "observed_at"]).reset_index(drop=True)

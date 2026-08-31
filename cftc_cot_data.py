# -*- coding: utf-8 -*-
"""موصل CFTC COT التاريخي الرسمي للذهب COMEX.

يستخدم ملفات Futures Only السنوية المنشورة من CFTC. تاريخ التقرير هو
الثلاثاء، لكن البيانات لا تصبح متاحة حتى إصدار الجمعة؛ لذلك نضيف 3 أيام
ونمنع الباكتيست من رؤيتها قبل ذلك.
"""
from __future__ import annotations

import io
import re
import zipfile

import pandas as pd
import requests

from point_in_time import normalize_records


URL = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
COMBINED_URL = "https://www.cftc.gov/files/dea/history/deacot1986_2016.zip"
UA = {"User-Agent": "GoldCouncil/1.0 research contact=local"}


def _norm(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _find(columns, *candidates):
    lookup = {_norm(c): c for c in columns}
    for candidate in candidates:
        key = _norm(candidate)
        if key in lookup:
            return lookup[key]
    return None


def parse_archive(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members = [n for n in archive.namelist() if not n.endswith("/")]
        if not members:
            return pd.DataFrame()
        with archive.open(members[0]) as stream:
            raw = pd.read_csv(stream, low_memory=False)
    market_col = _find(raw.columns, "Market and Exchange Names", "Market_and_Exchange_Names")
    date_col = _find(raw.columns, "Report Date as YYYY-MM-DD",
                     "As of Date in Form YYYY-MM-DD", "As_of_Date_In_Form_YYMMDD")
    oi_col = _find(raw.columns, "Open Interest (All)", "Open_Interest_All")
    nc_long = _find(raw.columns, "Noncommercial Positions-Long (All)",
                    "NonComm_Positions_Long_All")
    nc_short = _find(raw.columns, "Noncommercial Positions-Short (All)",
                     "NonComm_Positions_Short_All")
    c_long = _find(raw.columns, "Commercial Positions-Long (All)",
                   "Comm_Positions_Long_All")
    c_short = _find(raw.columns, "Commercial Positions-Short (All)",
                    "Comm_Positions_Short_All")
    required = [market_col, date_col, oi_col, nc_long, nc_short]
    if any(c is None for c in required):
        raise ValueError("unsupported CFTC schema")
    mask = raw[market_col].astype(str).str.contains("GOLD", case=False, na=False)
    gold = raw.loc[mask].copy()
    observed = pd.to_datetime(gold[date_col].astype(str), errors="coerce", utc=True)
    if observed.isna().all():
        observed = pd.to_datetime(gold[date_col].astype(str), format="%y%m%d",
                                  errors="coerce", utc=True)
    out = pd.DataFrame({
        "observed": observed,
        "open_interest": pd.to_numeric(gold[oi_col], errors="coerce"),
        "noncommercial_long": pd.to_numeric(gold[nc_long], errors="coerce"),
        "noncommercial_short": pd.to_numeric(gold[nc_short], errors="coerce"),
        "commercial_long": pd.to_numeric(gold[c_long], errors="coerce") if c_long else None,
        "commercial_short": pd.to_numeric(gold[c_short], errors="coerce") if c_short else None,
    }).dropna(subset=["observed", "open_interest", "noncommercial_long",
                      "noncommercial_short"])
    out["noncommercial_net"] = out["noncommercial_long"] - out["noncommercial_short"]
    if c_long and c_short:
        out["commercial_net"] = out["commercial_long"] - out["commercial_short"]
    out["released"] = out["observed"] + pd.Timedelta(days=3, hours=21)
    out["available"] = out["released"]
    return normalize_records(out, observed_col="observed", released_col="released",
                             available_col="available", source="cftc_cot_legacy_futures")


def _fetch_url(url: str, label: str, timeout=60) -> pd.DataFrame:
    try:
        response = requests.get(url, headers=UA, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        status = exc.response.status_code if exc.response is not None else "network"
        raise RuntimeError(f"CFTC download failed for {label} (status={status})") from None
    return parse_archive(response.content)


def fetch_year(year: int, timeout=60) -> pd.DataFrame:
    return _fetch_url(URL.format(year=year), str(year), timeout)


def fetch_range(start_year: int, end_year: int) -> pd.DataFrame:
    frames = []
    if start_year <= 2016:
        combined = _fetch_url(COMBINED_URL, "1986-2016", timeout=120)
        observed_year = pd.to_datetime(combined["observed_at"], utc=True).dt.year
        frames.append(combined.loc[(observed_year >= start_year) &
                                   (observed_year <= min(end_year, 2016))])
    first_annual = max(start_year, 2017)
    frames.extend(fetch_year(year) for year in range(first_annual, end_year + 1))
    if not frames:
        return pd.DataFrame()
    return (pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["observed_at"], keep="last")
            .sort_values("available_at").reset_index(drop=True))

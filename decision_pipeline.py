# -*- coding: utf-8 -*-
"""مسار القرار الموحد للواجهة والجدولة والاختبار التاريخي.

هذه الوحدة هي نقطة التجميع الوحيدة للوكلاء. المستدعي يحدد صراحةً زمن
القرار والبيانات المتاحة له، لذلك لا يحتاج الباكتيست إلى أي اتصال حي.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

import agents
import council
import indicators
import macro_regime_agent
import cross_asset_agent
import cot_agent
import seasonality_agent
import event_calendar_agent
import pattern_agent
import systematic_regime_agent
import news_impact_agent
import economic_surprise_agent
from risk_engine import position_size


ROOT = Path(__file__).resolve().parent
DEFAULT_MACRO_PATH = ROOT / "data_cache" / "macro_point_in_time_2008_2026.csv"
DEFAULT_EVENTS_PATH = ROOT / "data_cache" / "events_2008_2026.csv"
DEFAULT_SURPRISE_PATH = ROOT / "data_cache" / "economic_calendar_snapshots.csv"


@lru_cache(maxsize=4)
def _read_csv_cached(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def clear_data_caches() -> None:
    """Invalidate live CSV snapshots after an atomic collector update."""
    _read_csv_cached.cache_clear()


def load_macro_history(path: str | Path = DEFAULT_MACRO_PATH) -> pd.DataFrame | None:
    file = Path(path)
    if not file.exists():
        return None
    return _read_csv_cached(str(file.resolve())).copy()


def load_surprise_history(path: str | Path = DEFAULT_SURPRISE_PATH) -> pd.DataFrame | None:
    file = Path(path)
    if not file.exists():
        return None
    return _read_csv_cached(str(file.resolve())).copy()


def _as_utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def apply_risk_sizing(decision: dict, capital: float, risk_pct: float) -> dict:
    """يحوّل معامل المخاطرة إلى حجم قابل للتنفيذ بدلاً من عرضه فقط."""
    levels = decision.get("levels") or {}
    multiplier = max(0.0, min(1.0, float(decision.get("risk_multiplier", 1.0))))
    base_oz = 0.0
    if decision.get("signal") in (1, -1) and levels.get("entry") and levels.get("sl"):
        base_oz = position_size(
            float(levels["entry"]), float(levels["sl"]), float(capital), float(risk_pct)
        )
    effective_oz = round(base_oz * multiplier, 4)
    decision["base_position_oz"] = base_oz
    decision["position_oz"] = effective_oz
    decision["risk_budget_usd"] = round(float(capital) * float(risk_pct) / 100 * multiplier, 2)
    decision["exposure_pct"] = round(multiplier * 100, 1) if effective_oz else 0.0
    return decision


def run_decision(
    daily: pd.DataFrame,
    news: list,
    *,
    spot_price: float | None = None,
    capital: float = 10000.0,
    risk_pct: float = 1.0,
    as_of=None,
    macro_history: pd.DataFrame | None = None,
    load_cached_macro: bool = False,
    events_path: str | Path = DEFAULT_EVENTS_PATH,
    aggregation_mode: str = "family",
    strategy_profile: str = "strategic",
    news_event_history: pd.DataFrame | None = None,
    surprise_history: pd.DataFrame | None = None,
    load_cached_surprises: bool = False,
) -> dict:
    """يشغّل المجلس كاملاً من بيانات صريحة ويعيد قراراً وسياقه.

    ``load_cached_macro`` مخصص للمسار الحي. الباكتيست يمرر لقطة التاريخ
    بنفسه حتى لا يصبح التحميل المحلي الضمني باباً لتسرب المستقبل.
    """
    if daily is None or daily.empty:
        raise ValueError("لا توجد بيانات أسعار لاتخاذ القرار")

    frame = daily.copy()
    if "time" not in frame.columns:
        frame = frame.reset_index()
        if "time" not in frame.columns:
            frame = frame.rename(columns={frame.columns[0]: "time"})
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
    if len(frame) < 210:
        raise ValueError(f"بيانات الأسعار غير كافية: {len(frame)} جلسة؛ المطلوب 210 على الأقل")
    if "atr" not in frame.columns:
        frame = indicators.add_all(frame)

    decision_at = _as_utc(as_of if as_of is not None else frame.iloc[-1]["time"])
    last_price = float(spot_price or frame.iloc[-1]["close"])
    atr_value = float(frame.iloc[-1]["atr"])
    ema200 = float(frame.iloc[-1]["ema200"])
    trend_bias = 1.0 if last_price > ema200 else -1.0
    levels = indicators.support_resistance(frame)
    warnings: list[str] = []

    reports = [
        agents.news_scout(news, as_of=decision_at),
        agents.macro_analyst(news, as_of=decision_at),
        agents.technical_analyst(frame),
        systematic_regime_agent.systematic_regime_agent(frame),
        seasonality_agent.seasonality_agent(frame, ref_date=decision_at),
        event_calendar_agent.event_calendar_agent(
            ref=decision_at, events_path=str(Path(events_path).resolve())
        ),
        pattern_agent.pattern_agent(frame.set_index("time")),
        agents.risk_manager(frame, capital, risk_pct),
        agents.expert_scout(news),
        news_impact_agent.news_impact_agent(news_event_history, as_of=decision_at),
    ]

    if surprise_history is None and load_cached_surprises:
        surprise_history = load_surprise_history()
    reports.append(economic_surprise_agent.economic_surprise_agent(
        surprise_history, as_of=decision_at
    ))

    if macro_history is None and load_cached_macro:
        macro_history = load_macro_history()
    if macro_history is not None and not macro_history.empty:
        reports.extend([
            macro_regime_agent.macro_regime_agent(macro_history, as_of=decision_at),
            cross_asset_agent.cross_asset_from_history(
                frame[["time", "close"]], macro_history, as_of=decision_at
            ),
            cot_agent.cot_positioning_agent(macro_history, as_of=decision_at),
        ])
    else:
        warnings.append("بيانات الماكرو/COT الموحدة غير متاحة؛ خُفضت تغطية الأدلة")

    decision = council.chairman_decision(
        reports, levels, atr_value, last_price,
        trend_bias=trend_bias, ema200=ema200,
        aggregation_mode=aggregation_mode,
        strategy_profile=strategy_profile,
    )
    apply_risk_sizing(decision, capital, risk_pct)
    decision["decision_at"] = decision_at.isoformat()
    decision["pipeline_warnings"] = warnings
    return {
        "dec": decision,
        "reports": reports,
        "last_price": last_price,
        "daily": frame,
        "context": {
            "atr": atr_value,
            "ema200": ema200,
            "rsi": float(frame.iloc[-1]["rsi"]),
            "volatility_pct": atr_value / last_price * 100,
            "macd_hist": float(frame.iloc[-1]["macd_hist"]),
            "trend_bias": trend_bias,
            "decision_at": decision_at,
        },
    }

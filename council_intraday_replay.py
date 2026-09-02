# -*- coding: utf-8 -*-
"""Causal intraday replay of the exact council decision pipeline.

The strategic agents see only completed daily bars before the decision date.
Execution and scoring use the first M15 bar at/after the event, then measure
15/60/240-minute outcomes with observed spread and explicit slippage.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

import backtester_v5
import council
import decision_pipeline
import indicators
from mt5_event_history import event_return_summary


ROOT = Path(__file__).resolve().parent
DEFAULT_DAILY = ROOT / "data_cache" / "mt5_d1_2019_2026.csv"
DEFAULT_BARS = ROOT / "data_cache" / "mt5_event_bars_m15_2020_2025.csv"
DEFAULT_MACRO = ROOT / "data_cache" / "macro_point_in_time_2008_2026.csv"
DEFAULT_NEWS = ROOT / "gold_news_master.csv"
DEFAULT_NEWS_LABELS = ROOT / "data_cache" / "official_event_news_labels.csv"
DEFAULT_SURPRISES = ROOT / "data_cache" / "economic_surprises_2020_2025.csv"
HORIZONS = (15, 60, 240)
MT5_GOLD_POINT = 0.01


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _read_optional(path: str | Path) -> pd.DataFrame | None:
    file = Path(path)
    return pd.read_csv(file, low_memory=False) if file.exists() else None


def net_directed_return(raw_return_pct: float, signal: int, *,
                        spread_cost_pct: float = 0.0,
                        slippage_bps_per_side: float = 2.5) -> float:
    roundtrip_slippage_pct = 2 * float(slippage_bps_per_side) / 100
    return float(signal) * float(raw_return_pct) - float(spread_cost_pct) - roundtrip_slippage_pct


def simulate_live_exit(window: pd.DataFrame, decision: dict, *,
                       point: float = MT5_GOLD_POINT,
                       slippage_bps_per_side: float = 2.5) -> dict:
    """Replay the same TP1/SL/4h exit policy used by the MT5 DEMO bridge.

    MT5 bars are bid bars. A long enters at ask, while a short exits at ask.
    If both TP and SL occur inside one M15 bar, the conservative SL outcome is
    chosen because intrabar ordering is unknowable from OHLC data.
    """
    signal = int(decision.get("signal", 0) or 0)
    levels = decision.get("levels") or {}
    post = window.copy()
    if "phase" in post:
        post = post[post["phase"].eq("after")].copy()
    post = post.sort_values("time").head(max(HORIZONS) // 15)
    required = ("entry", "sl", "tp1")
    if signal not in (-1, 1) or post.empty or any(levels.get(key) is None for key in required):
        return {"status": "not_executable", "net_return_pct": None}

    first = post.iloc[0]
    bid_entry = float(first["open"])
    spread_points = float(first.get("spread", 0) or 0)
    spread_price = spread_points * float(point)
    model_entry = float(levels["entry"])
    stop_distance = abs(model_entry - float(levels["sl"]))
    target_distance = abs(float(levels["tp1"]) - model_entry)
    entry = bid_entry + spread_price if signal > 0 else bid_entry
    stop = entry - stop_distance if signal > 0 else entry + stop_distance
    target = entry + target_distance if signal > 0 else entry - target_distance

    exit_price = None
    exit_time = None
    exit_reason = "time_4h"
    for _, bar in post.iterrows():
        bar_spread = float(bar.get("spread", spread_points) or 0) * float(point)
        if signal > 0:
            stop_hit = float(bar["low"]) <= stop
            target_hit = float(bar["high"]) >= target
        else:
            # A short is closed against the ask side of the market.
            stop_hit = float(bar["high"]) + bar_spread >= stop
            target_hit = float(bar["low"]) + bar_spread <= target
        if stop_hit:
            exit_price, exit_reason = stop, "sl"
        elif target_hit:
            exit_price, exit_reason = target, "tp1"
        if exit_price is not None:
            exit_time = bar["time"]
            break

    if exit_price is None:
        last = post.iloc[-1]
        last_spread = float(last.get("spread", spread_points) or 0) * float(point)
        exit_price = float(last["close"]) if signal > 0 else float(last["close"]) + last_spread
        exit_time = last["time"]

    gross = signal * (float(exit_price) / entry - 1.0) * 100
    net = gross - 2 * float(slippage_bps_per_side) / 100
    return {
        "status": "ok",
        "entry_price": round(entry, 6),
        "exit_price": round(float(exit_price), 6),
        "exit_time": pd.Timestamp(exit_time).isoformat(),
        "exit_reason": exit_reason,
        "gross_return_pct": round(gross, 6),
        "net_return_pct": round(net, 6),
    }


def _wilson(wins: int, total: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    p = wins / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return 100 * (centre - margin), 100 * (centre + margin)


def summarize_trades(frame: pd.DataFrame, horizons=HORIZONS) -> dict:
    output = {
        "decision_count": int(len(frame)),
        "signal_count": int((pd.to_numeric(frame.get("signal"), errors="coerce") != 0).sum())
        if len(frame) else 0,
    }
    output["hold_count"] = output["decision_count"] - output["signal_count"]
    output["coverage_pct"] = round(
        100 * output["signal_count"] / output["decision_count"], 2
    ) if output["decision_count"] else 0.0
    for horizon in horizons:
        column = f"net_{horizon}m_pct"
        eligible = pd.to_numeric(frame.get(column), errors="coerce").dropna()
        wins = eligible[eligible > 0]
        losses = eligible[eligible <= 0]
        low, high = _wilson(len(wins), len(eligible))
        gross_profit = float(wins.sum())
        gross_loss = abs(float(losses.sum()))
        output[f"horizon_{horizon}m"] = {
            "trades": int(len(eligible)),
            "wins": int(len(wins)),
            "win_rate_pct": round(100 * len(wins) / len(eligible), 2) if len(eligible) else None,
            "wilson_95_low_pct": round(low, 2) if low is not None else None,
            "wilson_95_high_pct": round(high, 2) if high is not None else None,
            "mean_net_return_pct": round(float(eligible.mean()), 4) if len(eligible) else None,
            "median_net_return_pct": round(float(eligible.median()), 4) if len(eligible) else None,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        }
    if "execution_net_240m_pct" in frame:
        eligible = pd.to_numeric(frame["execution_net_240m_pct"], errors="coerce").dropna()
        wins = eligible[eligible > 0]
        losses = eligible[eligible <= 0]
        low, high = _wilson(len(wins), len(eligible))
        gross_profit = float(wins.sum())
        gross_loss = abs(float(losses.sum()))
        output["execution_240m"] = {
            "trades": int(len(eligible)),
            "wins": int(len(wins)),
            "win_rate_pct": round(100 * len(wins) / len(eligible), 2) if len(eligible) else None,
            "wilson_95_low_pct": round(low, 2) if low is not None else None,
            "wilson_95_high_pct": round(high, 2) if high is not None else None,
            "mean_net_return_pct": round(float(eligible.mean()), 4) if len(eligible) else None,
            "median_net_return_pct": round(float(eligible.median()), 4) if len(eligible) else None,
            "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
            "exit_reasons": (
                frame.loc[eligible.index, "execution_exit_reason"].value_counts().to_dict()
                if "execution_exit_reason" in frame else {}
            ),
        }
    return output


def _agent_attribution(rows: pd.DataFrame, horizons=HORIZONS) -> dict:
    results = {}
    score_columns = [name for name in rows.columns if name.startswith("agent_")]
    for column in score_columns:
        key = column.removeprefix("agent_").removesuffix("_score")
        scores = pd.to_numeric(rows[column], errors="coerce")
        active = scores.abs() > 10
        if not active.any():
            continue
        item = {"active_observations": int(active.sum())}
        for horizon in horizons:
            raw = pd.to_numeric(rows[f"raw_{horizon}m_pct"], errors="coerce")
            costs = pd.to_numeric(rows["spread_cost_pct"], errors="coerce").fillna(0) + 0.05
            directed = scores.map(lambda value: 1 if value > 10 else -1 if value < -10 else 0) * raw - costs
            eligible = directed[active & raw.notna()]
            item[f"{horizon}m"] = {
                "n": int(len(eligible)),
                "accuracy_pct": round(float((eligible > 0).mean() * 100), 2) if len(eligible) else None,
                "mean_directed_return_pct": round(float(eligible.mean()), 4) if len(eligible) else None,
            }
        results[key] = item
    return results


def _decision_windows(bars: pd.DataFrame, *, decision_hour_utc: int = 18,
                      step_trading_days: int = 1):
    """Yield event windows or one non-overlapping routine decision per trading day."""
    if {"event_time", "event_type", "phase"}.issubset(bars.columns):
        for (event_time, event_type), window in bars.groupby(
                ["event_time", "event_type"], sort=True):
            yield _utc(event_time), str(event_type), window
        return
    candidates = bars[
        (bars["time"].dt.hour == int(decision_hour_utc))
        & (bars["time"].dt.minute == 0)
    ].sort_values("time")
    if step_trading_days > 1:
        candidates = candidates.iloc[::int(step_trading_days)]
    for decision_time in candidates["time"]:
        end = decision_time + pd.Timedelta(minutes=max(HORIZONS))
        window = bars[(bars["time"] >= decision_time) & (bars["time"] < end)].copy()
        if len(window) < max(HORIZONS) // 15:
            continue
        window["phase"] = "after"
        window["event_time"] = decision_time
        window["entry_time"] = decision_time
        yield _utc(decision_time), "ROUTINE", window


def run_replay(*, daily_path=DEFAULT_DAILY, bars_path=DEFAULT_BARS,
               macro_path=DEFAULT_MACRO, news_path=DEFAULT_NEWS,
               news_labels_path=DEFAULT_NEWS_LABELS,
               surprises_path=DEFAULT_SURPRISES,
               events_path=decision_pipeline.DEFAULT_EVENTS_PATH,
               start="2023-01-01", end="2025-10-01",
               slippage_bps_per_side=2.5, risk_pct=0.25,
               aggregation_mode="family", decision_hour_utc=18,
               step_trading_days=1,
               strategy_profile="strategic") -> tuple[dict, pd.DataFrame]:
    daily = pd.read_csv(daily_path, low_memory=False)
    daily["time"] = pd.to_datetime(daily["time"], errors="coerce", utc=True)
    daily = daily.dropna(subset=["time", "close"]).sort_values("time")
    bars = pd.read_csv(bars_path, low_memory=False)
    for column in ("time", "event_time", "entry_time"):
        if column in bars:
            bars[column] = pd.to_datetime(bars[column], errors="coerce", utc=True)
    bars = bars.dropna(subset=["time"]).sort_values("time")
    start_at, end_at = _utc(start), _utc(end)
    time_key = "event_time" if "event_time" in bars else "time"
    bars = bars[(bars[time_key] >= start_at) & (bars[time_key] < end_at)]
    macro = _read_optional(macro_path)
    news_labels = _read_optional(news_labels_path)
    surprises = _read_optional(surprises_path)
    news = backtester_v5.load_news_csv(str(news_path)) if Path(news_path).exists() else []

    rows = []
    ablation_rows = []
    for event_time, event_type, window in _decision_windows(
            bars, decision_hour_utc=decision_hour_utc,
            step_trading_days=step_trading_days):
        window = window.sort_values("time").drop_duplicates("time")
        post = window[window["phase"].eq("after")]
        if post.empty:
            continue
        decision_time = _utc(post.iloc[0]["time"])
        # A daily row is timestamped near the session open. Exclude the whole
        # decision date so its future close can never leak into the council.
        daily_cutoff = decision_time.floor("D")
        daily_history = daily[daily["time"] < daily_cutoff].copy()
        if len(daily_history) < 253:
            continue
        news_start = decision_time - pd.Timedelta(hours=72)
        known_news = [
            item for item in news
            if item.get("published") is not None
            and news_start.to_pydatetime() <= item["published"] <= decision_time.to_pydatetime()
        ]
        spot = float(post.iloc[0]["open"])
        result = decision_pipeline.run_decision(
            daily_history, known_news, spot_price=spot, capital=10_000,
            risk_pct=risk_pct, as_of=decision_time,
            macro_history=macro, load_cached_macro=False,
            events_path=events_path, aggregation_mode=aggregation_mode,
            strategy_profile=strategy_profile,
            news_event_history=news_labels, surprise_history=surprises,
        )
        decision = result["dec"]
        returns = event_return_summary(window, timeframe_minutes=15, horizons_minutes=HORIZONS)
        if returns.get("status") != "ok":
            continue
        spread_cost = float(returns.get("spread_cost_pct", 0) or 0)
        row = {
            "decision_time": decision_time.isoformat(),
            "event_type": event_type,
            "entry_price": spot,
            "signal": int(decision["signal"]),
            "decision": decision["decision"],
            "final_score": float(decision["final_score"]),
            "confidence": float(decision["confidence"]),
            "agreement": float(decision["agreement"]),
            "quality_passed": bool(decision["quality_passed"]),
            "vetoed": decision.get("vetoed"),
            "risk_multiplier": float(decision.get("risk_multiplier", 0)),
            "supporting_family_count": len(decision.get("supporting_families", [])),
            "spread_cost_pct": spread_cost,
        }
        for horizon in HORIZONS:
            with_spread = returns.get(f"return_{horizon}m_pct")
            raw = None if with_spread is None else float(with_spread) + spread_cost
            row[f"raw_{horizon}m_pct"] = raw
            row[f"net_{horizon}m_pct"] = (
                net_directed_return(raw, int(decision["signal"]),
                                    spread_cost_pct=spread_cost,
                                    slippage_bps_per_side=slippage_bps_per_side)
                if raw is not None and int(decision["signal"]) != 0 else None
            )
        execution = simulate_live_exit(
            window, decision,
            slippage_bps_per_side=slippage_bps_per_side,
        )
        row["execution_net_240m_pct"] = execution.get("net_return_pct")
        row["execution_exit_reason"] = execution.get("exit_reason")
        row["execution_exit_time"] = execution.get("exit_time")
        for report in result["reports"]:
            row[f"agent_{report.key}_score"] = float(report.score)
        for family, score in decision.get("family_scores", {}).items():
            row[f"family_{family}_score"] = float(score)
        rows.append(row)

        strategic = result["daily"]
        levels = indicators.support_resistance(strategic)
        context = result["context"]
        for removed_key in council.WEIGHTS_V2:
            reduced = [report for report in result["reports"] if report.key != removed_key]
            alternate = council.chairman_decision(
                reduced, levels, context["atr"], spot,
                trend_bias=context["trend_bias"], ema200=context["ema200"],
                aggregation_mode=aggregation_mode,
                strategy_profile=strategy_profile,
            )
            raw_240 = row.get("raw_240m_pct")
            alternate_signal = int(alternate["signal"])
            ablation_rows.append({
                "removed_agent": removed_key,
                "signal": alternate_signal,
                "net_240m_pct": net_directed_return(
                    raw_240, alternate_signal, spread_cost_pct=spread_cost,
                    slippage_bps_per_side=slippage_bps_per_side,
                ) if raw_240 is not None and alternate_signal else None,
            })

    decisions = pd.DataFrame(rows)
    if decisions.empty:
        return {"error": "no replayable decisions"}, decisions
    summary = summarize_trades(decisions)
    summary.update({
        "period": {"start": start_at.isoformat(), "end_exclusive": end_at.isoformat()},
        "cost_model": {
            "observed_mt5_spread": True,
            "slippage_bps_per_side": float(slippage_bps_per_side),
        },
        "decision_schedule": {
            "mode": "event" if "event_time" in bars else "routine",
            "hour_utc": int(decision_hour_utc) if "event_time" not in bars else None,
            "step_trading_days": int(step_trading_days),
        },
        "strategy_profile": strategy_profile,
        "event_type_breakdown": {
            str(kind): summarize_trades(group)
            for kind, group in decisions.groupby("event_type")
        },
        "year_breakdown": {
            str(year): summarize_trades(group)
            for year, group in decisions.groupby(pd.to_datetime(decisions["decision_time"]).dt.year)
        },
        "agent_attribution": _agent_attribution(decisions),
    })
    ablations = pd.DataFrame(ablation_rows)
    summary["ablation_240m"] = {
        key: summarize_trades(group, horizons=(240,))["horizon_240m"]
        | {"signal_count": int((group["signal"] != 0).sum())}
        for key, group in ablations.groupby("removed_agent")
    } if not ablations.empty else {}
    return summary, decisions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--daily", default=str(DEFAULT_DAILY))
    parser.add_argument("--bars", default=str(DEFAULT_BARS))
    parser.add_argument("--macro", default=str(DEFAULT_MACRO))
    parser.add_argument("--news", default=str(DEFAULT_NEWS))
    parser.add_argument("--news-labels", default=str(DEFAULT_NEWS_LABELS))
    parser.add_argument("--surprises", default=str(DEFAULT_SURPRISES))
    parser.add_argument("--events", default=str(decision_pipeline.DEFAULT_EVENTS_PATH))
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2025-10-01")
    parser.add_argument("--slippage-bps-per-side", type=float, default=2.5)
    parser.add_argument("--risk-pct", type=float, default=0.25)
    parser.add_argument("--aggregation-mode", choices=("family", "agent"), default="family")
    parser.add_argument("--decision-hour-utc", type=int, default=18)
    parser.add_argument("--step-trading-days", type=int, default=1)
    parser.add_argument("--strategy-profile", choices=tuple(council.COUNCIL_PROFILES),
                        default="strategic")
    parser.add_argument("--report", default="data_cache/council_intraday_replay_report.json")
    parser.add_argument("--decisions", default="data_cache/council_intraday_replay_decisions.csv")
    args = parser.parse_args()
    report, decisions = run_replay(
        daily_path=args.daily, bars_path=args.bars, macro_path=args.macro,
        news_path=args.news, news_labels_path=args.news_labels,
        surprises_path=args.surprises, events_path=args.events,
        start=args.start, end=args.end,
        slippage_bps_per_side=args.slippage_bps_per_side,
        risk_pct=args.risk_pct, aggregation_mode=args.aggregation_mode,
        decision_hour_utc=args.decision_hour_utc,
        step_trading_days=args.step_trading_days,
        strategy_profile=args.strategy_profile,
    )
    report_path = Path(args.report)
    decisions_path = Path(args.decisions)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    decisions.to_csv(decisions_path, index=False, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

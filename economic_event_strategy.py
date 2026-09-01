# -*- coding: utf-8 -*-
"""مختبر استراتيجية المفاجأة الاقتصادية على ذهب MT5 داخل اليوم.

القواعد ثابتة وسببية: Actual المتاح، أول افتتاح M15 عند/بعد الإصدار، ATR من
شموع ما قبل الخبر فقط، وقف واحد، ثم خروج زمني بعد أربع ساعات. لا يحتوي هذا
الملف أي اتصال حي أو إرسال أوامر.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class EventStrategyConfig:
    timeframe_minutes: int = 15
    holding_minutes: int = 240
    atr_period: int = 14
    sl_atr_mult: float = 2.0
    slippage_per_side_pct: float = 0.025
    risk_pct: float = 0.25
    daily_loss_limit_pct: float = 0.50
    min_abs_score: float = 10.0
    skip_component_conflicts: bool = True
    point: float = 0.01
    allowed_event_types: tuple[str, ...] = ("CPI", "NFP")


def aggregate_event_signals(surprises: pd.DataFrame,
                            min_abs_score: float = 10.0) -> pd.DataFrame:
    frame = surprises.copy()
    frame["event_time"] = pd.to_datetime(frame["release_time"], errors="coerce", utc=True)
    frame["gold_score"] = pd.to_numeric(frame["gold_score"], errors="coerce")
    frame["component_signal"] = frame["gold_score"].apply(
        lambda x: 1 if x > min_abs_score else -1 if x < -min_abs_score else 0
    )
    grouped = frame.groupby(["event_time", "event_type"], as_index=False).agg(
        gold_score=("gold_score", "mean"),
        component_count=("title", "size"),
        positive_components=("component_signal", lambda x: int((x > 0).sum())),
        negative_components=("component_signal", lambda x: int((x < 0).sum())),
        availability_assumption=("availability_assumption", "first"),
    )
    grouped["component_conflict"] = (
        (grouped["positive_components"] > 0) & (grouped["negative_components"] > 0)
    )
    grouped["signal"] = grouped["gold_score"].apply(
        lambda x: 1 if x > min_abs_score else -1 if x < -min_abs_score else 0
    )
    return grouped


def pre_event_atr(window: pd.DataFrame, period: int = 14) -> float | None:
    before = window[window["phase"] == "before"].copy().sort_values("time")
    if len(before) < period + 1:
        return None
    previous_close = pd.to_numeric(before["close"], errors="coerce").shift(1)
    high = pd.to_numeric(before["high"], errors="coerce")
    low = pd.to_numeric(before["low"], errors="coerce")
    true_range = pd.concat([
        high - low, (high - previous_close).abs(), (low - previous_close).abs()
    ], axis=1).max(axis=1)
    value = true_range.dropna().tail(period).mean()
    return float(value) if pd.notna(value) and value > 0 else None


def simulate_event(window: pd.DataFrame, signal_row, config: EventStrategyConfig) -> dict | None:
    frame = window.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
    post = frame[frame["phase"] == "after"].sort_values("time").copy()
    atr = pre_event_atr(frame, config.atr_period)
    if post.empty or atr is None:
        return None
    direction = int(signal_row.signal)
    if direction not in (-1, 1):
        return None
    entry_bar = post.iloc[0]
    entry_time = pd.Timestamp(entry_bar["time"])
    entry = float(entry_bar["open"])
    stop_distance = float(config.sl_atr_mult) * atr
    stop = entry - direction * stop_distance
    deadline = entry_time + pd.Timedelta(minutes=config.holding_minutes)
    eligible = post[post["time"] < deadline]
    if eligible.empty:
        return None

    exit_price = float(eligible.iloc[-1]["close"])
    exit_time = pd.Timestamp(eligible.iloc[-1]["time"]) + pd.Timedelta(
        minutes=config.timeframe_minutes
    )
    exit_reason = "time_exit"
    mae_pct, mfe_pct = 0.0, 0.0
    for row in eligible.itertuples():
        if direction == 1:
            mae_pct = min(mae_pct, (float(row.low) / entry - 1.0) * 100)
            mfe_pct = max(mfe_pct, (float(row.high) / entry - 1.0) * 100)
            if float(row.low) <= stop:
                exit_price = stop; exit_time = pd.Timestamp(row.time); exit_reason = "atr_stop"
                break
        else:
            mae_pct = min(mae_pct, (entry / float(row.high) - 1.0) * 100)
            mfe_pct = max(mfe_pct, (entry / float(row.low) - 1.0) * 100)
            if float(row.high) >= stop:
                exit_price = stop; exit_time = pd.Timestamp(row.time); exit_reason = "atr_stop"
                break

    spread_points = float(entry_bar.get("spread", 0) or 0)
    spread_price = spread_points * config.point
    slippage_price = entry * (2 * config.slippage_per_side_pct / 100)
    roundtrip_cost_price = spread_price + slippage_price
    gross_per_oz = direction * (exit_price - entry)
    net_per_oz = gross_per_oz - roundtrip_cost_price
    risk_per_oz = stop_distance + roundtrip_cost_price
    return {
        "event_time": pd.Timestamp(signal_row.event_time),
        "event_type": signal_row.event_type,
        "signal": direction,
        "gold_score": float(signal_row.gold_score),
        "component_count": int(signal_row.component_count),
        "component_conflict": bool(signal_row.component_conflict),
        "entry_time": entry_time, "entry_price": entry,
        "atr": atr, "stop_price": stop, "exit_time": exit_time,
        "exit_price": exit_price, "exit_reason": exit_reason,
        "spread_points": spread_points,
        "roundtrip_cost_price": roundtrip_cost_price,
        "gross_return_pct": gross_per_oz / entry * 100,
        "net_return_pct": net_per_oz / entry * 100,
        "r_multiple": net_per_oz / risk_per_oz,
        "mae_pct": mae_pct, "mfe_pct": mfe_pct,
    }


def run_strategy(surprises: pd.DataFrame, bars: pd.DataFrame,
                 config: EventStrategyConfig, *, starting_equity=10_000.0) -> pd.DataFrame:
    signals = aggregate_event_signals(surprises, config.min_abs_score)
    signals = signals[signals["event_type"].isin(config.allowed_event_types)]
    bars = bars.copy()
    bars["event_time"] = pd.to_datetime(bars["event_time"], errors="coerce", utc=True)
    bars["time"] = pd.to_datetime(bars["time"], errors="coerce", utc=True)
    windows = {
        key: group for key, group in bars.groupby(["event_time", "event_type"])
    }
    equity = float(starting_equity)
    day_start_equity = equity
    current_day = None
    rows = []
    for signal in signals.sort_values("event_time").itertuples():
        if signal.signal == 0:
            continue
        if config.skip_component_conflicts and signal.component_conflict:
            continue
        day = pd.Timestamp(signal.event_time).date()
        if day != current_day:
            current_day, day_start_equity = day, equity
        daily_return = (equity / day_start_equity - 1.0) * 100 if day_start_equity else 0.0
        if daily_return <= -config.daily_loss_limit_pct:
            continue
        window = windows.get((pd.Timestamp(signal.event_time), signal.event_type))
        if window is None:
            continue
        trade = simulate_event(window, signal, config)
        if trade is None:
            continue
        risk_budget = equity * config.risk_pct / 100
        risk_per_oz = abs(trade["entry_price"] - trade["stop_price"]) \
            + trade["roundtrip_cost_price"]
        position_oz = risk_budget / risk_per_oz if risk_per_oz > 0 else 0.0
        pnl_usd = trade["r_multiple"] * risk_budget
        equity += pnl_usd
        rows.append({**trade, "risk_budget_usd": risk_budget,
                     "position_oz": position_oz, "pnl_usd": pnl_usd,
                     "equity_after": equity})
    return pd.DataFrame(rows)


def _profit_factor(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors="coerce").dropna()
    gains = values[values > 0].sum(); losses = -values[values < 0].sum()
    return float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)


def summarize(trades: pd.DataFrame, *, starting_equity=10_000.0) -> dict:
    if trades is None or trades.empty:
        return {"trades": 0, "profit_factor": 0.0}
    pnl = pd.to_numeric(trades["pnl_usd"], errors="coerce").fillna(0.0)
    # أعد بناء المنحنى من PnL المجموعة نفسها؛ ``equity_after`` قد يكون تراكمياً
    # من فترة أوسع عند تلخيص سنة منفردة.
    equity = pd.concat([
        pd.Series([starting_equity], dtype=float),
        starting_equity + pnl.cumsum().reset_index(drop=True),
    ], ignore_index=True)
    peak = equity.cummax()
    drawdown = (peak - equity) / peak * 100
    factor = _profit_factor(pnl)
    return {
        "trades": len(trades), "wins": int((pnl > 0).sum()),
        "win_rate_pct": round(float((pnl > 0).mean() * 100), 2),
        "profit_factor": "inf" if math.isinf(factor) else round(factor, 4),
        "expectancy_usd": round(float(pnl.mean()), 2),
        "mean_net_return_pct": round(float(trades["net_return_pct"].mean()), 4),
        "mean_r_multiple": round(float(trades["r_multiple"].mean()), 4),
        "stop_hit_pct": round(float((trades["exit_reason"] == "atr_stop").mean() * 100), 2),
        "total_return_pct": round(float((equity.iloc[-1] / starting_equity - 1) * 100), 4),
        "max_drawdown_pct": round(float(drawdown.max()), 4),
    }


def select_on_discovery(surprises: pd.DataFrame, bars: pd.DataFrame,
                        base: EventStrategyConfig, *, split_date="2023-01-01",
                        sl_grid=(1.0, 1.5, 2.0, 2.5, 3.0, 4.0)) -> tuple[EventStrategyConfig, list[dict]]:
    split = pd.Timestamp(split_date, tz="UTC")
    s = surprises.copy(); s["release_time"] = pd.to_datetime(s["release_time"], utc=True)
    b = bars.copy(); b["event_time"] = pd.to_datetime(b["event_time"], utc=True)
    discovery_s = s[s["release_time"] < split]
    discovery_b = b[b["event_time"] < split]
    candidates = []
    for multiplier in sl_grid:
        config = replace(base, sl_atr_mult=float(multiplier))
        trades = run_strategy(discovery_s, discovery_b, config)
        metrics = summarize(trades)
        factor = metrics.get("profit_factor", 0.0)
        numeric_factor = 999.0 if factor == "inf" else float(factor)
        candidates.append({"sl_atr_mult": multiplier, **metrics,
                           "selection_score": numeric_factor})
    eligible = [row for row in candidates if row["trades"] >= 30]
    if not eligible:
        raise RuntimeError("no discovery configuration has at least 30 trades")
    winner = max(eligible, key=lambda row: (row["selection_score"], row["expectancy_usd"]))
    return replace(base, sl_atr_mult=float(winner["sl_atr_mult"])), candidates


def audit(surprises: pd.DataFrame, bars: pd.DataFrame,
          base: EventStrategyConfig, *, split_date="2023-01-01") -> tuple[pd.DataFrame, dict]:
    selected, candidates = select_on_discovery(
        surprises, bars, base, split_date=split_date
    )
    split = pd.Timestamp(split_date, tz="UTC")
    surprises = surprises.copy(); bars = bars.copy()
    surprises["release_time"] = pd.to_datetime(surprises["release_time"], utc=True)
    bars["event_time"] = pd.to_datetime(bars["event_time"], utc=True)
    discovery = run_strategy(surprises[surprises["release_time"] < split],
                             bars[bars["event_time"] < split], selected)
    validation = run_strategy(surprises[surprises["release_time"] >= split],
                              bars[bars["event_time"] >= split], selected)
    validation = validation.copy(); validation["sample"] = "validation"
    discovery = discovery.copy(); discovery["sample"] = "discovery"
    all_trades = pd.concat([discovery, validation], ignore_index=True)
    yearly = {
        str(year): summarize(group)
        for year, group in validation.groupby(validation["event_time"].dt.year)
    } if not validation.empty else {}
    by_event_type = {
        str(event_type): summarize(group)
        for event_type, group in validation.groupby("event_type")
    } if not validation.empty else {}
    report = {
        "research_only": True, "demo_execution_enabled": False,
        "selected_only_on_discovery": True,
        "split_date": split.isoformat(), "selected_config": asdict(selected),
        "discovery_grid": candidates,
        "discovery": summarize(discovery), "validation": summarize(validation),
        "validation_by_year": yearly,
        "validation_by_event_type": by_event_type,
        "next_shadow_candidate": {
            "allowed_event_types": ["NFP"],
            "reason": "post-validation 2025 CPI deterioration; requires fresh 2026 shadow data",
            "not_an_independent_backtest": True,
        },
        "limitations": [
            "historical actual capture timestamp unavailable",
            "M15 OHLC cannot reveal tick order inside a bar; stop is assumed first",
            "2026 remains reserved for live shadow validation",
        ],
    }
    return all_trades, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surprises", default="data_cache/economic_surprises_2020_2025.csv")
    parser.add_argument("--bars", default="data_cache/mt5_event_bars_m15_2020_2025.csv")
    parser.add_argument("--split-date", default="2023-01-01")
    parser.add_argument("--trades-out", default="data_cache/economic_event_strategy_trades.csv")
    parser.add_argument("--report-out", default="data_cache/economic_event_strategy_report.json")
    args = parser.parse_args()
    trades, report = audit(pd.read_csv(args.surprises), pd.read_csv(args.bars),
                           EventStrategyConfig(), split_date=args.split_date)
    Path(args.trades_out).parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(args.trades_out, index=False, encoding="utf-8")
    Path(args.report_out).write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                                default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

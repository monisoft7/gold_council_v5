# -*- coding: utf-8 -*-
"""تقرير أداء الصفقات المنفذة بواسطة جسر مجلس الذهب على MT5 DEMO."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json

from env_loader import env
from mt5_demo_bridge import MAGIC, MT5ConnectionConfig, MT5DemoBridge


def summarize_deals(deals) -> dict:
    rows = [deal._asdict() if hasattr(deal, "_asdict") else dict(deal) for deal in deals]
    rows = [row for row in rows if int(row.get("magic", -1)) == MAGIC]
    positions: dict[int, list[dict]] = {}
    for row in rows:
        position_id = int(row.get("position_id", row.get("position", 0)) or 0)
        positions.setdefault(position_id, []).append(row)
    closed = []
    for position_id, items in positions.items():
        # DEAL_ENTRY_IN=0؛ أي قيمة أخرى تعني خروجاً كلياً/جزئياً أو انعكاساً.
        if not any(int(item.get("entry", 0)) != 0 for item in items):
            continue
        pnl = sum(
            float(item.get("profit", 0) or 0)
            + float(item.get("commission", 0) or 0)
            + float(item.get("swap", 0) or 0)
            + float(item.get("fee", 0) or 0)
            for item in items
        )
        closed_at = max(int(item.get("time_msc", 0) or 0) for item in items)
        closed.append({"position_id": position_id, "pnl": pnl, "closed_at": closed_at})
    closed.sort(key=lambda item: item["closed_at"])
    pnls = [item["pnl"] for item in closed]
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value <= 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    equity, peak, max_drawdown = 0.0, 0.0, 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        "closed_positions": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
        "net_profit": round(sum(pnls), 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_profit / gross_loss, 3) if gross_loss else None,
        "max_drawdown_money": round(max_drawdown, 2),
    }


def real_account_gate(report: dict, *, days: int, starting_equity: float) -> dict:
    """سياسة موضوعية؛ مرور الوقت وحده لا يكفي للانتقال إلى حساب حقيقي."""
    checks = {
        "minimum_30_closed_positions": int(report.get("closed_positions", 0)) >= 30,
        "minimum_30_calendar_days": int(days) >= 30,
        # Win rate alone is not a quality gate when wins and losses have
        # different sizes. Profit factor measures frequency and payoff.
        "profit_factor_at_least_1_25": float(report.get("profit_factor") or 0) >= 1.25,
        "drawdown_below_5pct": float(report.get("max_drawdown_money") or 0)
        <= float(starting_equity) * 0.05,
    }
    return {"eligible_for_real": all(checks.values()), "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    login_text = env.get("MT5_LOGIN")
    config = MT5ConnectionConfig(
        terminal_path=env.get("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"),
        login=int(login_text) if login_text else None,
        password=env.get("MT5_PASSWORD"), server=env.get("MT5_SERVER"),
        symbol=env.get("MT5_SYMBOL", "XAUUSD"),
    )
    bridge = MT5DemoBridge(config)
    try:
        account = bridge.connect()
        date_to = datetime.now(timezone.utc)
        deals = bridge.mt5.history_deals_get(
            date_to - timedelta(days=args.days), date_to, group=f"*{bridge.symbol}*"
        )
        if deals is None:
            raise RuntimeError(f"تعذر قراءة سجل MT5: {bridge.mt5.last_error()}")
        report = summarize_deals(deals)
        report["account_suffix"] = account["account_suffix"]
        report["symbol"] = bridge.symbol
        report["days"] = args.days
        report["real_account_gate"] = real_account_gate(
            report, days=args.days, starting_equity=account["equity"]
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        bridge.shutdown()


if __name__ == "__main__":
    main()

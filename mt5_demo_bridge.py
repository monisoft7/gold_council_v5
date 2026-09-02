# -*- coding: utf-8 -*-
"""جسر MetaTrader 5 محمي: حساب تجريبي فقط وشراء/انتظار فقط.

لا يرسل أي أمر إلا عند تمرير ``execute=True``، وبعد التحقق من أن نوع
الحساب DEMO وفحص الطلب عبر ``order_check``. الحساب الحقيقي مرفوض برمجياً.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import pandas as pd


MAGIC = 26083101


class MT5SafetyError(RuntimeError):
    pass


@dataclass
class MT5ConnectionConfig:
    terminal_path: str = ""
    login: int | None = None
    password: str = ""
    server: str = ""
    symbol: str = "XAUUSD"
    deviation: int = 20


class MT5DemoBridge:
    def __init__(self, config: MT5ConnectionConfig, mt5_module=None):
        if mt5_module is None:
            import MetaTrader5 as mt5_module
        self.mt5 = mt5_module
        self.config = config
        self.account = None
        self.symbol = None

    def connect(self) -> dict:
        kwargs: dict[str, Any] = {}
        if self.config.login is not None:
            kwargs["login"] = int(self.config.login)
        if self.config.password:
            kwargs["password"] = self.config.password
        if self.config.server:
            kwargs["server"] = self.config.server
        if self.config.terminal_path:
            ok = self.mt5.initialize(self.config.terminal_path, **kwargs)
        else:
            ok = self.mt5.initialize(**kwargs)
        if not ok:
            raise RuntimeError(f"فشل اتصال MT5: {self.mt5.last_error()}")

        self.account = self.mt5.account_info()
        if self.account is None:
            raise RuntimeError(f"تعذر قراءة حساب MT5: {self.mt5.last_error()}")
        if self.account.trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise MT5SafetyError("رفض الاتصال: الجسر يسمح بحساب MT5 DEMO فقط")
        if not bool(getattr(self.account, "trade_allowed", False)):
            raise MT5SafetyError("التداول غير مسموح في حساب MT5 الحالي")
        if not bool(getattr(self.account, "trade_expert", False)):
            raise MT5SafetyError("التداول الآلي غير مسموح في حساب MT5 الحالي")

        terminal = self.mt5.terminal_info()
        if terminal is None or not bool(getattr(terminal, "connected", False)):
            raise RuntimeError("طرفية MT5 غير متصلة بخادم الوسيط")
        self.symbol = self.resolve_symbol(self.config.symbol)
        return {
            "account_suffix": str(self.account.login)[-4:],
            "server": self.account.server,
            "balance": float(self.account.balance),
            "equity": float(self.account.equity),
            "symbol": self.symbol,
            "demo": True,
        }

    def shutdown(self) -> None:
        self.mt5.shutdown()

    def resolve_symbol(self, requested: str) -> str:
        if self.mt5.symbol_info(requested) is not None:
            if not self.mt5.symbol_select(requested, True):
                raise RuntimeError(f"تعذر تفعيل الرمز {requested} في Market Watch")
            return requested
        candidates = list(self.mt5.symbols_get(group="*XAU*") or [])
        candidates += list(self.mt5.symbols_get(group="*GOLD*") or [])
        names = sorted({item.name for item in candidates})
        if not names:
            raise RuntimeError(f"لم يُعثر على رمز ذهب قريب من {requested}")
        preferred = next((name for name in names if "XAUUSD" in name.upper()), names[0])
        if not self.mt5.symbol_select(preferred, True):
            raise RuntimeError(f"تعذر تفعيل رمز الذهب {preferred}")
        return preferred

    def closed_daily_bars(self, count: int = 600) -> pd.DataFrame:
        # start_pos=1 يستبعد شمعة اليوم غير المكتملة ويحافظ على تكافؤ الباكتيست.
        rates = self.mt5.copy_rates_from_pos(
            self.symbol, self.mt5.TIMEFRAME_D1, 1, int(count)
        )
        if rates is None or len(rates) < 253:
            raise RuntimeError(f"شموع MT5 اليومية غير كافية: {0 if rates is None else len(rates)}")
        frame = pd.DataFrame(rates)
        frame["time"] = pd.to_datetime(frame["time"], unit="s", utc=True)
        frame["volume"] = frame.get("real_volume", frame.get("tick_volume", 0))
        return frame[["time", "open", "high", "low", "close", "volume"]]

    def current_ask(self) -> float:
        tick = self.mt5.symbol_info_tick(self.symbol)
        if tick is None or float(tick.ask) <= 0:
            raise RuntimeError(f"لا يوجد سعر ask صالح للرمز {self.symbol}")
        return float(tick.ask)

    @staticmethod
    def _floor_volume(raw: float, minimum: float, maximum: float, step: float) -> float:
        if raw < minimum or step <= 0:
            return 0.0
        steps = math.floor((min(raw, maximum) + 1e-12) / step)
        return round(steps * step, 8)

    def build_buy_request(self, decision: dict) -> dict | None:
        if decision.get("signal") != 1 or not decision.get("quality_passed"):
            return None
        if float(decision.get("risk_multiplier", 0)) <= 0:
            return None
        info = self.mt5.symbol_info(self.symbol)
        tick = self.mt5.symbol_info_tick(self.symbol)
        if info is None or tick is None:
            raise RuntimeError("تعذر قراءة خصائص رمز الذهب")
        contract_size = float(getattr(info, "trade_contract_size", 0) or 0)
        if contract_size <= 0:
            raise RuntimeError("حجم العقد غير صالح؛ لا يمكن تحويل الأونصات إلى lots")
        desired_lots = float(decision.get("position_oz", 0)) / contract_size
        volume = self._floor_volume(
            desired_lots,
            float(info.volume_min), float(info.volume_max), float(info.volume_step),
        )
        if volume <= 0:
            return None
        levels = decision.get("levels") or {}
        digits = int(getattr(info, "digits", 2))
        supported_filling = {
            getattr(self.mt5, "ORDER_FILLING_FOK", -1),
            self.mt5.ORDER_FILLING_IOC,
            getattr(self.mt5, "ORDER_FILLING_RETURN", -2),
        }
        filling_mode = int(getattr(info, "filling_mode", self.mt5.ORDER_FILLING_IOC))
        if filling_mode not in supported_filling:
            filling_mode = self.mt5.ORDER_FILLING_IOC
        return {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": volume,
            "type": self.mt5.ORDER_TYPE_BUY,
            "price": round(float(tick.ask), digits),
            "sl": round(float(levels["sl"]), digits),
            "tp": round(float(levels["tp1"]), digits),
            "deviation": int(self.config.deviation),
            "magic": MAGIC,
            "comment": "gold_council_demo",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

    def submit_decision(self, decision: dict, *, execute: bool = False) -> dict:
        if self.account is None or self.symbol is None:
            raise RuntimeError("يجب الاتصال بـMT5 قبل تقييم الأمر")
        if self.account.trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise MT5SafetyError("حظر نهائي: الحساب ليس DEMO")
        positions = self.mt5.positions_get(symbol=self.symbol)
        if positions is None:
            raise RuntimeError(f"تعذر فحص المراكز المفتوحة: {self.mt5.last_error()}")
        if positions:
            return {"status": "skipped", "reason": "يوجد مركز مفتوح على رمز الذهب"}
        request = self.build_buy_request(decision)
        if request is None:
            return {"status": "skipped", "reason": "لا توجد إشارة قابلة للتنفيذ أو الحجم دون حد الوسيط"}
        checked = self.mt5.order_check(request)
        if checked is None:
            raise RuntimeError(f"order_check فشل: {self.mt5.last_error()}")
        check_dict = checked._asdict()
        if int(check_dict.get("retcode", -1)) != 0:
            return {"status": "rejected", "stage": "order_check", "check": check_dict}
        if not execute:
            return {"status": "dry_run", "request": request, "check": check_dict}
        result = self.mt5.order_send(request)
        if result is None:
            raise RuntimeError(f"order_send فشل: {self.mt5.last_error()}")
        result_dict = result._asdict()
        accepted = int(result_dict.get("retcode", -1)) in {
            self.mt5.TRADE_RETCODE_DONE,
            getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", -999),
            getattr(self.mt5, "TRADE_RETCODE_PLACED", -998),
        }
        return {
            "status": "submitted" if accepted else "rejected",
            "stage": "order_send",
            "result": result_dict,
        }

    def close_expired_positions(self, *, now=None, max_age_minutes: int = 240,
                                execute: bool = False) -> dict:
        """Close only this project's DEMO positions after the tested 4h horizon."""
        if self.account is None or self.symbol is None:
            raise RuntimeError("يجب الاتصال بـMT5 قبل إدارة المراكز")
        if self.account.trade_mode != self.mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise MT5SafetyError("حظر نهائي: الحساب ليس DEMO")
        positions = self.mt5.positions_get(symbol=self.symbol)
        if positions is None:
            raise RuntimeError(f"تعذر فحص المراكز المفتوحة: {self.mt5.last_error()}")
        current = pd.Timestamp(now or pd.Timestamp.now(tz="UTC"))
        current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
        actions = []
        managed_position_count = 0
        for position in positions:
            if int(getattr(position, "magic", -1)) != MAGIC:
                continue
            managed_position_count += 1
            opened = pd.Timestamp(int(position.time), unit="s", tz="UTC")
            age_minutes = (current - opened).total_seconds() / 60
            if age_minutes < int(max_age_minutes):
                continue
            tick = self.mt5.symbol_info_tick(self.symbol)
            info = self.mt5.symbol_info(self.symbol)
            if tick is None or info is None:
                raise RuntimeError("تعذر قراءة السعر لإغلاق المركز الزمني")
            is_buy = int(position.type) == int(getattr(self.mt5, "POSITION_TYPE_BUY", 0))
            close_type = self.mt5.ORDER_TYPE_SELL if is_buy else self.mt5.ORDER_TYPE_BUY
            close_price = float(tick.bid if is_buy else tick.ask)
            request = {
                "action": self.mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": float(position.volume),
                "type": close_type,
                "position": int(position.ticket),
                "price": round(close_price, int(getattr(info, "digits", 2))),
                "deviation": int(self.config.deviation),
                "magic": MAGIC,
                "comment": "gold_council_4h_exit",
                "type_time": self.mt5.ORDER_TIME_GTC,
                "type_filling": self.mt5.ORDER_FILLING_IOC,
            }
            checked = self.mt5.order_check(request)
            if checked is None:
                raise RuntimeError(f"order_check لإغلاق 4h فشل: {self.mt5.last_error()}")
            check_dict = checked._asdict()
            if int(check_dict.get("retcode", -1)) != 0:
                actions.append({"status": "rejected", "stage": "order_check",
                                "position": int(position.ticket), "check": check_dict})
                continue
            if not execute:
                actions.append({"status": "dry_run", "position": int(position.ticket),
                                "age_minutes": round(age_minutes, 1), "request": request})
                continue
            result = self.mt5.order_send(request)
            if result is None:
                raise RuntimeError(f"order_send لإغلاق 4h فشل: {self.mt5.last_error()}")
            result_dict = result._asdict()
            accepted = int(result_dict.get("retcode", -1)) in {
                self.mt5.TRADE_RETCODE_DONE,
                getattr(self.mt5, "TRADE_RETCODE_DONE_PARTIAL", -999),
                getattr(self.mt5, "TRADE_RETCODE_PLACED", -998),
            }
            actions.append({
                "status": "submitted" if accepted else "rejected",
                "stage": "order_send", "position": int(position.ticket),
                "age_minutes": round(age_minutes, 1), "result": result_dict,
            })
        return {
            "status": "ok", "actions": actions,
            "managed_position_count": managed_position_count,
            "max_age_minutes": int(max_age_minutes),
        }

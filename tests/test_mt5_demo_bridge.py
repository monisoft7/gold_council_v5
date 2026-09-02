from types import SimpleNamespace

import pytest

from mt5_demo_bridge import MT5ConnectionConfig, MT5DemoBridge, MT5SafetyError
from mt5_demo_report import real_account_gate, summarize_deals


class FakeResult:
    def __init__(self, **values):
        self.values = values

    def _asdict(self):
        return self.values.copy()


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    POSITION_TYPE_BUY = 0
    ORDER_TIME_GTC = 0
    ORDER_FILLING_IOC = 1
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008

    def __init__(self, trade_mode=0, positions=()):
        self.trade_mode = trade_mode
        self.sent = []
        self.positions = positions

    def initialize(self, *args, **kwargs): return True
    def shutdown(self): return True
    def last_error(self): return (0, "ok")
    def account_info(self):
        return SimpleNamespace(
            trade_mode=self.trade_mode, trade_allowed=True, trade_expert=True,
            login=12345678, server="Broker-Demo", balance=10000, equity=10000,
        )
    def terminal_info(self): return SimpleNamespace(connected=True)
    def symbol_info(self, symbol):
        return SimpleNamespace(
            name=symbol, trade_contract_size=100, volume_min=0.01,
            volume_max=100, volume_step=0.01, digits=2,
        )
    def symbol_select(self, symbol, selected): return True
    def symbols_get(self, group=None): return []
    def symbol_info_tick(self, symbol): return SimpleNamespace(ask=2500.0, bid=2499.5)
    def positions_get(self, symbol=None): return self.positions
    def order_check(self, request): return FakeResult(retcode=0, comment="ok")
    def order_send(self, request):
        self.sent.append(request)
        return FakeResult(retcode=self.TRADE_RETCODE_DONE, order=42)


def _decision():
    return {
        "signal": 1, "quality_passed": True, "risk_multiplier": 1.0,
        "position_oz": 1.0,
        "levels": {"sl": 2480.0, "tp1": 2540.0},
    }


def test_real_account_is_rejected_even_before_order_building():
    bridge = MT5DemoBridge(MT5ConnectionConfig(), FakeMT5(trade_mode=2))
    with pytest.raises(MT5SafetyError):
        bridge.connect()


def test_dry_run_checks_but_never_sends():
    fake = FakeMT5()
    bridge = MT5DemoBridge(MT5ConnectionConfig(), fake)
    bridge.connect()
    result = bridge.submit_decision(_decision(), execute=False)
    assert result["status"] == "dry_run"
    assert result["request"]["volume"] == 0.01
    assert fake.sent == []


def test_explicit_demo_execution_can_send_after_check():
    fake = FakeMT5()
    bridge = MT5DemoBridge(MT5ConnectionConfig(), fake)
    bridge.connect()
    result = bridge.submit_decision(_decision(), execute=True)
    assert result["status"] == "submitted"
    assert len(fake.sent) == 1


def test_position_below_broker_minimum_is_not_rounded_up():
    fake = FakeMT5()
    bridge = MT5DemoBridge(MT5ConnectionConfig(), fake)
    bridge.connect()
    decision = _decision()
    decision["position_oz"] = 0.5
    result = bridge.submit_decision(decision, execute=True)
    assert result["status"] == "skipped"
    assert fake.sent == []


def test_only_project_position_is_closed_after_four_hours():
    old = 1_700_000_000
    project = SimpleNamespace(
        magic=26083101, time=old, type=0, volume=0.01, ticket=77,
    )
    manual = SimpleNamespace(
        magic=123, time=old, type=0, volume=0.01, ticket=88,
    )
    fake = FakeMT5(positions=(project, manual))
    bridge = MT5DemoBridge(MT5ConnectionConfig(), fake)
    bridge.connect()
    result = bridge.close_expired_positions(
        now="2023-11-15T03:13:20Z", max_age_minutes=240, execute=True,
    )
    assert len(result["actions"]) == 1
    assert result["actions"][0]["status"] == "submitted"
    assert fake.sent[0]["position"] == 77
    assert fake.sent[0]["type"] == fake.ORDER_TYPE_SELL


def test_demo_report_aggregates_closed_positions_after_costs():
    deals = [
        {"magic": 26083101, "position_id": 1, "entry": 0, "profit": 0,
         "commission": -1, "swap": 0, "fee": 0, "time_msc": 1},
        {"magic": 26083101, "position_id": 1, "entry": 1, "profit": 21,
         "commission": 0, "swap": 0, "fee": 0, "time_msc": 2},
        {"magic": 26083101, "position_id": 2, "entry": 0, "profit": 0,
         "commission": -1, "swap": 0, "fee": 0, "time_msc": 3},
        {"magic": 26083101, "position_id": 2, "entry": 1, "profit": -9,
         "commission": 0, "swap": 0, "fee": 0, "time_msc": 4},
    ]
    report = summarize_deals(deals)
    assert report["closed_positions"] == 2
    assert report["win_rate_pct"] == 50.0
    assert report["net_profit"] == 10.0
    assert report["profit_factor"] == 2.0


def test_real_account_gate_requires_sample_quality_not_time_only():
    weak = {
        "closed_positions": 2, "win_rate_pct": 100,
        "profit_factor": 5, "max_drawdown_money": 0,
    }
    assert real_account_gate(weak, days=30, starting_equity=10_000)["eligible_for_real"] is False
    strong = {
        "closed_positions": 30, "win_rate_pct": 60,
        "profit_factor": 1.5, "max_drawdown_money": 300,
    }
    assert real_account_gate(strong, days=30, starting_equity=10_000)["eligible_for_real"] is True

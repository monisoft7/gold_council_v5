# -*- coding: utf-8 -*-
"""اختبارات المقاييس المؤسسية."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import metrics


def test_max_drawdown_exact():
    # قمة 110 ثم هبوط إلى 90 → (110-90)/110 = 18.18%
    assert abs(metrics.max_drawdown([100, 110, 90, 95]) - 18.18) < 0.01
    assert metrics.max_drawdown([]) == 0.0


def test_profit_factor_and_expectancy():
    assert metrics.profit_factor([2, 3, -1]) == 5.0
    assert metrics.profit_factor([-1, -2]) == 0.0
    assert metrics.expectancy([2, -1, 3]) == 4 / 3


def test_sharpe_sign():
    assert metrics.sharpe([0.01] * 10 + [0.0] * 2) > 0
    assert metrics.sharpe([-0.01] * 10) < 0


def test_summarize_keys():
    s = metrics.summarize([2.9, -1.95, 2.9, 2.9, -1.95])
    for k in ["trades", "total_return_pct", "max_drawdown_pct",
              "sharpe", "profit_factor", "expectancy_pct"]:
        assert k in s
    assert s["trades"] == 5

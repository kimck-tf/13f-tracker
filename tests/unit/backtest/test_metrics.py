import math

import numpy as np
import pytest

from thirteen_f.backtest.metrics import (
    total_return,
    cagr,
    sharpe,
    sortino,
    max_drawdown,
    calmar,
    win_rate_quarterly,
)


def test_total_return():
    navs = [100.0, 110.0, 121.0]
    assert total_return(navs) == pytest.approx(0.21)


def test_cagr_one_year():
    # 252 영업일 = 1년, +10%
    navs = [100.0] * 251 + [110.0]
    assert cagr(navs, num_days=252) == pytest.approx(0.10, abs=1e-3)


def test_sharpe_positive_return():
    # 안정적 +0.1% 일간 수익률 → 높은 샤프
    returns = [0.001] * 252
    s = sharpe(returns)
    assert s > 10  # 단순화: 무위험률 0


def test_sortino_no_down_days():
    returns = [0.001] * 252
    # 하방 분산 0 → infinity 처리 안전
    s = sortino(returns)
    assert s == float("inf") or s > 100


def test_max_drawdown():
    navs = [100, 120, 80, 100, 60]
    # peak=120 → 60 → mdd=(120-60)/120=0.5
    assert max_drawdown(navs) == pytest.approx(0.5)


def test_calmar():
    # CAGR/MDD = 0.10/0.50 = 0.2
    assert calmar(cagr_value=0.10, mdd_value=0.50) == pytest.approx(0.2)


def test_calmar_mdd_zero():
    # MDD가 0이면 무한대(또는 0 처리). 안전하게 inf 또는 0 반환
    result = calmar(cagr_value=0.10, mdd_value=0.0)
    assert math.isinf(result) or result == 0


def test_win_rate_quarterly():
    # 4 분기: +5%, -2%, +10%, +1% → 3/4 = 0.75
    quarter_pnls = [0.05, -0.02, 0.10, 0.01]
    assert win_rate_quarterly(quarter_pnls) == pytest.approx(0.75)

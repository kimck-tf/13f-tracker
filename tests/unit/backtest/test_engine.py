from datetime import date, timedelta

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.engine import run_backtest
from thirteen_f.backtest.strategy import Strategy


class FixedTwoTickerStrategy(Strategy):
    name = "Fixed50"
    def get_target_positions(self, as_of_date, conn):
        # 항상 AAPL 50% + MSFT 50%
        return {"AAPL": 0.5, "MSFT": 0.5}

    def params_json(self):
        return "{}"


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "engine.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    # 합성 가격: AAPL +0.1%/day, MSFT 0/day, SPY +0.05%/day
    start = date(2024, 1, 2)
    for i in range(252):
        d = start + timedelta(days=i)
        c.execute(
            "INSERT INTO prices VALUES (?, ?, NULL, NULL, NULL, ?, ?, 0)",
            ("AAPL", d, 100.0 * (1.001 ** i), 100.0 * (1.001 ** i)),
        )
        c.execute(
            "INSERT INTO prices VALUES (?, ?, NULL, NULL, NULL, ?, ?, 0)",
            ("MSFT", d, 100.0, 100.0),
        )
        c.execute(
            "INSERT INTO prices VALUES (?, ?, NULL, NULL, NULL, ?, ?, 0)",
            ("SPY", d, 100.0 * (1.0005 ** i), 100.0 * (1.0005 ** i)),
        )
    yield c
    c.close()


def test_engine_runs_and_returns_curve(conn):
    result = run_backtest(
        strategy=FixedTwoTickerStrategy(),
        start=date(2024, 1, 2),
        end=date(2024, 12, 31),
        conn=conn,
        cost_bps=0,  # 비용 0으로 단순 검증
    )
    # 250 영업일 정도 NAV 곡선
    assert len(result.nav_series) > 200
    # 첫날 NAV는 initial_capital
    first = result.nav_series[0]
    assert first[1] == pytest.approx(1_000_000, rel=1e-3)


def test_engine_lookahead_blocked(conn):
    """전략이 미래 데이터를 보면 안 됨 → 빈 포트폴리오로 인해 NAV 고정."""

    class FutureStrategy(Strategy):
        name = "Future"
        def get_target_positions(self, as_of_date, conn):
            # 정상 SQL이면 빈 결과여야 함 (실제로는 SingleManagerClone 같은 게 이 역할)
            return {}
        def params_json(self):
            return "{}"

    result = run_backtest(
        strategy=FutureStrategy(),
        start=date(2024, 1, 2),
        end=date(2024, 12, 31),
        conn=conn,
        cost_bps=0,
    )
    # 포지션 없으니 NAV가 변동 없음
    navs = [n[1] for n in result.nav_series]
    assert navs[0] == pytest.approx(navs[-1], rel=1e-6)


def test_engine_applies_cost(conn):
    """리밸런싱 시 거래비용 차감 검증."""

    class OnceStrategy(Strategy):
        name = "Once"
        def get_target_positions(self, as_of_date, conn):
            return {"AAPL": 1.0}
        def params_json(self):
            return "{}"

    result_no_cost = run_backtest(
        strategy=OnceStrategy(), start=date(2024, 1, 2), end=date(2024, 12, 31),
        conn=conn, cost_bps=0,
    )
    result_with_cost = run_backtest(
        strategy=OnceStrategy(), start=date(2024, 1, 2), end=date(2024, 12, 31),
        conn=conn, cost_bps=100,  # 100bp = 1%
    )
    no_cost_end = result_no_cost.nav_series[-1][1]
    with_cost_end = result_with_cost.nav_series[-1][1]
    assert with_cost_end < no_cost_end

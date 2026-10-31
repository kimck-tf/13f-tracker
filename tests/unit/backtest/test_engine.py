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


def test_engine_persists_quarterly_holdings(conn):
    """Phase 5 A4: persist=True 시 분기 첫 영업일의 weights가 backtest_holdings에 저장."""
    result = run_backtest(
        strategy=FixedTwoTickerStrategy(),
        start=date(2024, 1, 2),
        end=date(2024, 12, 31),
        conn=conn,
        cost_bps=0,
        persist=True,
    )
    # 분기 4개 (Q1~Q4) 만큼 snapshot 누적
    assert len(result.holdings_log) >= 2
    # DB에 저장됐는지 검증
    rows = conn.execute(
        """
        SELECT DISTINCT rebalance_date FROM backtest_holdings
        WHERE run_id = ? ORDER BY rebalance_date
        """,
        (result.run_id,),
    ).fetchall()
    assert len(rows) >= 2
    # 같은 분기의 weights 합 ≈ 1.0
    first_date = rows[0][0]
    total_weight = conn.execute(
        "SELECT SUM(weight) FROM backtest_holdings WHERE run_id = ? AND rebalance_date = ?",
        (result.run_id, first_date),
    ).fetchone()[0]
    assert abs(total_weight - 1.0) < 1e-6
    # 종목은 AAPL + MSFT 둘 다 등장
    tickers = {
        t for (t,) in conn.execute(
            "SELECT DISTINCT ticker FROM backtest_holdings WHERE run_id = ?",
            (result.run_id,),
        ).fetchall()
    }
    assert tickers == {"AAPL", "MSFT"}


def test_benchmark_nav_tracks_spy_before_first_position(conn):
    """벤치마크 NAV는 전략이 첫 종목을 사기 전에도 SPY를 따라야 한다 — 그렇지 않으면 첫 매수
    시점이 다른 전략끼리 bench_cagr가 달라져(15.56% vs 16.29%) 초과수익 비교가 어긋난다."""

    class CashOnly(Strategy):
        name = "CashOnly"
        def get_target_positions(self, as_of_date, conn):
            return {}
        def params_json(self):
            return "{}"

    result = run_backtest(
        strategy=CashOnly(), start=date(2024, 1, 2), end=date(2024, 12, 31),
        conn=conn, cost_bps=0,
    )
    # SPY +0.05%/day, 252일 → 251번 상승
    assert result.metrics["bench_total_return"] == pytest.approx(1.0005 ** 251 - 1, rel=1e-6)


def test_engine_drops_tickers_whose_prices_stopped(conn):
    """MSFT 가격이 2024-06-30에 끊기면 10일 뒤부터 포지션에서 빠지고 비중은 AAPL 100%가 된다."""
    conn.execute("DELETE FROM prices WHERE ticker = 'MSFT' AND date > DATE '2024-06-30'")
    result = run_backtest(
        strategy=FixedTwoTickerStrategy(),
        start=date(2024, 1, 2),
        end=date(2024, 12, 31),
        conn=conn,
        cost_bps=0,
    )
    counts = {d: n for d, _, _, n in result.nav_series}
    assert counts[date(2024, 6, 28)] == 2
    assert counts[date(2024, 7, 10)] == 2  # 06-30 + 10일까지는 유지
    assert counts[date(2024, 7, 11)] == 1
    assert counts[date(2024, 7, 12)] == 1 and counts[date(2024, 9, 9)] == 1
    navs = {d: v for d, v, _, _ in result.nav_series}
    # 남은 AAPL이 100% — 07-12 → 09-09(59일) NAV가 AAPL처럼 하루 0.1%씩 오른다
    assert navs[date(2024, 9, 9)] / navs[date(2024, 7, 12)] == pytest.approx(1.001**59)


def test_engine_skips_tickers_without_any_price(conn):
    """가격이 한 번도 없는 종목은 살 수 없다 — 비중을 받지 못하고 나머지가 100%가 된다."""

    class WithUnpriced(Strategy):
        name = "WithUnpriced"

        def get_target_positions(self, as_of_date, conn):
            return {"AAPL": 0.5, "ZZZ": 0.5}

        def params_json(self):
            return "{}"

    result = run_backtest(
        strategy=WithUnpriced(),
        start=date(2024, 1, 2),
        end=date(2024, 3, 31),
        conn=conn,
        cost_bps=0,
    )
    assert {n for _, _, _, n in result.nav_series} == {1}
    navs = [v for _, v, _, _ in result.nav_series]
    assert navs[-1] / navs[0] == pytest.approx(1.001 ** (len(navs) - 1))


def test_engine_rebuy_does_not_earn_the_return_made_while_out(conn):
    """4월에 AAPL을 팔고(MSFT 100%) 5월 1일에 다시 사면, 그날 수익에 AAPL의 4월 상승(+3%)이
    붙으면 안 된다 — 판 종목의 마지막 가격이 남아 있으면 재매수일에 한꺼번에 들어온다.
    가격이 10일 넘게 끊겨 빠졌다가 돌아오는 종목(_drop_stale)도 같은 경로를 탄다."""

    class Rotate(Strategy):
        name = "Rotate"

        def get_target_positions(self, as_of_date, conn):
            if date(2024, 4, 1) <= as_of_date < date(2024, 5, 1):
                return {"MSFT": 1.0}
            return {"AAPL": 1.0}

        def params_json(self):
            return "{}"

    result = run_backtest(Rotate(), date(2024, 1, 2), date(2024, 6, 30), conn, cost_bps=0)
    navs = {d: v for d, v, _, _ in result.nav_series}
    assert navs[date(2024, 5, 1)] / navs[date(2024, 4, 30)] == pytest.approx(1.0, abs=1.5e-3)
    # 다시 산 뒤에는 AAPL을 그대로 따라간다
    assert navs[date(2024, 6, 30)] / navs[date(2024, 5, 1)] == pytest.approx(1.001**60)

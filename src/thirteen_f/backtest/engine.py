"""Backtest engine. Spec §7.3."""
from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Iterable

import duckdb

from thirteen_f.backtest.metrics import (
    cagr,
    calmar,
    max_drawdown,
    sharpe,
    sortino,
    total_return,
    win_rate_quarterly,
)
from thirteen_f.backtest.strategy import BacktestResult, Strategy

logger = logging.getLogger(__name__)


def _fetch_business_days(
    conn: duckdb.DuckDBPyConnection, benchmark: str, start: date, end: date
) -> list[date]:
    """벤치마크 가격이 있는 영업일 = 백테스트 영업일."""
    rows = conn.execute(
        """
        SELECT DISTINCT date FROM prices
        WHERE ticker = ? AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        (benchmark, start, end),
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_prices_for_day(
    conn: duckdb.DuckDBPyConnection, tickers: Iterable[str], d: date
) -> dict[str, float]:
    tickers = list(tickers)
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    rows = conn.execute(
        f"SELECT ticker, adj_close FROM prices WHERE date = ? AND ticker IN ({placeholders})",
        [d, *tickers],
    ).fetchall()
    return {r[0]: r[1] for r in rows if r[1] is not None}


def run_backtest(
    strategy: Strategy,
    start: date,
    end: date,
    conn: duckdb.DuckDBPyConnection,
    cost_bps: float = 10.0,
    benchmark: str = "SPY",
    initial_capital: float = 1_000_000.0,
    persist: bool = False,
) -> BacktestResult:
    """매 영업일 strategy.get_target_positions 호출.
    target != current 일 때만 리밸런싱 + cost_bps 편도 부과.
    """
    business_days = _fetch_business_days(conn, benchmark, start, end)
    if not business_days:
        raise ValueError(f"No prices for benchmark {benchmark} in {start}..{end}")

    # 상태
    portfolio_value = initial_capital
    bench_value = initial_capital
    current_weights: dict[str, float] = {}
    last_prices: dict[str, float] = {}
    last_bench_price: float | None = None

    nav_series: list[tuple[date, float, float, int]] = []
    quarter_navs: dict[str, float] = {}  # {quarter_label: nav at start}
    # Phase 5 A4: 분기 첫 영업일의 current_weights snapshot 누적 (backtest_holdings persist용)
    quarter_holdings: dict[str, tuple[date, dict[str, float]]] = {}

    from thirteen_f.core.dates import quarter_label

    for i, d in enumerate(business_days):
        target = strategy.get_target_positions(as_of_date=d, conn=conn)
        prices_today = _fetch_prices_for_day(
            conn, list(target.keys()) + list(current_weights.keys()) + [benchmark], d
        )
        # Spec §7.3 NULL 처리: 종목별 가격이 비면 last_prices의 값을 forward-fill로 사용
        # (상장폐지·비영업일·데이터 누락 시 직전 가격 유지 → 그날 수익률 0 효과)
        for t, p in last_prices.items():
            prices_today.setdefault(t, p)
        if last_bench_price is not None:
            prices_today.setdefault(benchmark, last_bench_price)

        # 거래비용 (target != current_weights 시) — i==0의 초기 진입도 포함
        # i==0: current_weights={} → Σ|target_w - 0| = Σtarget_w = 1.0 거래 → 첫날도 1회 비용 부과
        if target != current_weights:
            keys = set(target) | set(current_weights)
            trade_amount = sum(
                abs(target.get(t, 0) - current_weights.get(t, 0))
                for t in keys
            ) * portfolio_value
            cost = trade_amount * cost_bps / 10000.0
            portfolio_value -= cost
            current_weights = target.copy()

        # 일간 수익률 (i>0부터; 첫날은 portfolio_value=NAV 그대로)
        if i > 0 and last_prices:
            r = 0.0
            for t, w in current_weights.items():
                p_today = prices_today.get(t)
                p_yest = last_prices.get(t)
                if p_today and p_yest and p_yest > 0:
                    r += w * (p_today / p_yest - 1)
            portfolio_value *= (1 + r)
            p_b_t = prices_today.get(benchmark)
            if last_bench_price and p_b_t:
                bench_value *= p_b_t / last_bench_price

        # last_prices 업데이트: 오늘 가격 있는 종목만 갱신, 없는 종목은 직전 값 유지
        for t, p in prices_today.items():
            if t != benchmark and p is not None:
                last_prices[t] = p
        last_bench_price = prices_today.get(benchmark, last_bench_price)

        nav_series.append((d, portfolio_value, bench_value, len(current_weights)))
        q_lab = quarter_label(d)
        if q_lab not in quarter_navs:
            quarter_navs[q_lab] = portfolio_value
            if current_weights:
                quarter_holdings[q_lab] = (d, dict(current_weights))

    # 메트릭
    navs = [n[1] for n in nav_series]
    bench_navs = [n[2] for n in nav_series]
    daily_rets = [
        navs[i] / navs[i - 1] - 1 if navs[i - 1] > 0 else 0
        for i in range(1, len(navs))
    ]
    quarter_pnls: list[float] = []
    sorted_qs = sorted(quarter_navs.keys())
    for j in range(1, len(sorted_qs)):
        prev = quarter_navs[sorted_qs[j - 1]]
        curr_q = sorted_qs[j]
        curr_n = quarter_navs[curr_q]
        if prev > 0:
            quarter_pnls.append(curr_n / prev - 1)

    metrics = {
        "total_return": total_return(navs),
        "cagr": cagr(navs, num_days=len(navs)),
        "sharpe": sharpe(daily_rets),
        "sortino": sortino(daily_rets),
        "mdd": max_drawdown(navs),
        "calmar": calmar(cagr(navs, num_days=len(navs)), max_drawdown(navs)),
        "win_rate_quarterly": win_rate_quarterly(quarter_pnls),
        "bench_total_return": total_return(bench_navs),
        "bench_cagr": cagr(bench_navs, num_days=len(bench_navs)),
    }

    # I8: deep copy로 caller mutation이 engine internal state에 영향 없도록 격리
    holdings_log_copy = {
        q_lab: (rdate, dict(weights))
        for q_lab, (rdate, weights) in quarter_holdings.items()
    }
    result = BacktestResult(
        run_id=uuid.uuid4().hex,
        strategy_name=strategy.name,
        start_date=start,
        end_date=end,
        nav_series=nav_series,
        metrics=metrics,
        params_json=strategy.params_json(),
        benchmark=benchmark,
        cost_bps=cost_bps,
        holdings_log=holdings_log_copy,
    )

    if persist:
        _persist_result(conn, result)
    return result


def _persist_result(conn: duckdb.DuckDBPyConnection, r: BacktestResult) -> None:
    conn.execute(
        "INSERT INTO backtest_runs VALUES (?, ?, ?, ?, ?, ?, ?, now())",
        (r.run_id, r.strategy_name, r.params_json, r.start_date, r.end_date,
         r.benchmark, r.cost_bps),
    )
    conn.executemany(
        "INSERT INTO backtest_curves VALUES (?, ?, ?, ?, ?)",
        [(r.run_id, d, nav, bn, pc) for d, nav, bn, pc in r.nav_series],
    )
    m = r.metrics
    conn.execute(
        "INSERT INTO backtest_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (r.run_id, m["total_return"], m["cagr"], m["sharpe"], m["sortino"],
         m["mdd"], m["calmar"], m["win_rate_quarterly"],
         m["bench_total_return"], m["bench_cagr"]),
    )
    # Phase 5 A4: backtest_holdings — 분기 첫 영업일의 target snapshot
    # I5: run_id가 매번 uuid.uuid4().hex로 새 값이라 (run_id, rdate, ticker) PK 충돌 불가 →
    # 평범한 INSERT로 충분 (OR REPLACE는 의도 불명확이라 제거).
    rows = []
    for _q_lab, (rdate, weights) in r.holdings_log.items():
        for ticker, weight in weights.items():
            rows.append((r.run_id, rdate, ticker, weight))
    if rows:
        conn.executemany(
            "INSERT INTO backtest_holdings VALUES (?, ?, ?, ?)",
            rows,
        )

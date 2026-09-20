"""Multi-strategy runner. Spec §7.6."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import duckdb

from thirteen_f.backtest.engine import run_backtest
from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
from thirteen_f.backtest.strategies.conviction_follow import ConvictionFollow
from thirteen_f.backtest.strategies.ensemble import Ensemble
from thirteen_f.backtest.strategies.multi_manager import MultiManager
from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK
from thirteen_f.backtest.strategies.single_manager import SingleManagerClone

logger = logging.getLogger(__name__)


def default_suite() -> list:
    """Spec §7.2의 기본 6개 전략 + Phase 5의 MultiManager + 복제 비교용 Druckenmiller 복제.

    파라미터는 2026-09 탐색(docs/backtest-optimization-2026-09.md)의 계열별 최적값 — Calmar 기준,
    평균 보유 8종목 이상. SPA가 type당 최신 run 하나만 보여 주므로 type당 1개만 둔다.
    NewBuyOnly는 후보 풀이 작아 추천하지 않지만 화면 비교용으로 유지한다.
    """
    return [
        SingleManagerClone(label="Buffett"),
        SingleManagerClone(label="Druckenmiller"),
        ConsensusTopK(min_holders=3, top_k=10),
        ScoreTopK(top_k=40),
        ConvictionFollow(top_k=3),
        NewBuyOnly(min_holders=2, top_k=15),
        Ensemble(weights={
            ConsensusTopK(min_holders=3, top_k=10): 0.5,
            ConsensusTopK(min_holders=2, top_k=15): 0.5,
        }),
        MultiManager(mgr_labels=["Burry", "Dalio", "Druckenmiller", "Tepper"], top_k=20),
    ]


def run_suite(
    db_path: Path,
    start: date,
    end: date,
    cost_bps: float = 10.0,
    benchmark: str = "SPY",
) -> list[dict]:
    conn = duckdb.connect(str(db_path))
    try:
        results = []
        for strategy in default_suite():
            logger.info("Running %s ...", strategy.name)
            res = run_backtest(
                strategy=strategy,
                start=start,
                end=end,
                conn=conn,
                cost_bps=cost_bps,
                benchmark=benchmark,
                persist=True,
            )
            logger.info(
                "%s: CAGR=%.2f%% MDD=%.2f%% Sharpe=%.2f",
                strategy.name, res.metrics["cagr"] * 100,
                res.metrics["mdd"] * 100, res.metrics["sharpe"],
            )
            results.append({"name": strategy.name, "run_id": res.run_id, **res.metrics})
        return results
    finally:
        conn.close()

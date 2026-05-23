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
    """Spec §7.2의 기본 6개 전략 + Phase 5의 MultiManager(7th)."""
    return [
        SingleManagerClone(label="Buffett"),
        ConsensusTopK(min_holders=3, top_k=20),
        ScoreTopK(top_k=20),
        ConvictionFollow(top_k=10),
        NewBuyOnly(min_holders=2, top_k=15),
        Ensemble(weights={
            SingleManagerClone(label="Buffett"): 0.4,
            ScoreTopK(top_k=20): 0.4,
            ConsensusTopK(min_holders=3, top_k=20): 0.2,
        }),
        MultiManager(mgr_labels=["Buffett", "Ackman", "Tepper"], top_k=15),
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

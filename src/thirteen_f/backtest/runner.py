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


def strategy_by_name(name: str):
    """전략 이름 → 인스턴스. `cli.py`의 `backtest --strategy`·`targets --strategy`가 쓴다.

    받는 형식: `ScoreTopK`·`ConsensusTopK`·`ConvictionFollow`·`NewBuyOnly`·`MultiManager`(파라미터
    없는 이름은 `default_suite()`의 같은 type 전략 — 기본값을 suite 한 곳에만 둔다),
    `SingleManagerClone(<label>)`, `MultiManager(<label>,<label>[:top_k])`.
    """
    if name.startswith("SingleManagerClone("):
        return SingleManagerClone(label=name.split("(", 1)[1].rstrip(")"))
    if name.startswith("MultiManager("):
        body = name.split("(", 1)[1].rstrip(")")
        if ":" in body:
            labels_str, top_str = body.split(":", 1)
            top_k = int(top_str)
        else:
            labels_str, top_k = body, 15
        labels = [s.strip() for s in labels_str.split(",") if s.strip()]
        return MultiManager(mgr_labels=labels, top_k=top_k)
    # SingleManagerClone은 매니저를, Ensemble은 구성 전략을 이름으로 지정할 수 없어 제외
    by_type = {
        type(s).__name__: s
        for s in default_suite()
        if type(s).__name__ not in ("SingleManagerClone", "Ensemble")
    }
    if name in by_type:
        return by_type[name]
    raise ValueError(f"Unknown strategy: {name}")


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

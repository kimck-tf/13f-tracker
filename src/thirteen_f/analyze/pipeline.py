"""Phase 2 orchestration."""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.analyze.continuity import update_continuity_scores
from thirteen_f.analyze.conviction import update_conviction_scores
from thirteen_f.analyze.diff import compute_signals_quarterly
from thirteen_f.analyze.score import compute_total_scores, load_weights

logger = logging.getLogger(__name__)


def run_analyze(
    db_path: Path,
    scoring_toml: Path,
    diff_threshold: float = 0.05,
) -> dict[str, int]:
    weights = load_weights(scoring_toml)
    conn = duckdb.connect(str(db_path))
    try:
        n_signals = compute_signals_quarterly(conn, diff_threshold)
        logger.info("signals_quarterly: %d rows", n_signals)
        n_conv = update_conviction_scores(conn)
        logger.info("conviction updated: %d rows", n_conv)
        n_cont = update_continuity_scores(conn)
        logger.info("continuity updated: %d rows", n_cont)
        n_cons = compute_consensus(conn)
        logger.info("consensus: %d rows", n_cons)
        # manager_count는 None → compute_total_scores 내부에서 DB로부터 동적 derive
        n_total = compute_total_scores(conn, weights, manager_count=None)
        logger.info("total_scores: %d rows", n_total)
        return {
            "signals": n_signals,
            "conviction": n_conv,
            "continuity": n_cont,
            "consensus": n_cons,
            "total_scores": n_total,
        }
    finally:
        conn.close()

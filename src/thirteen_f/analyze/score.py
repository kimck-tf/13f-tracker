"""Total score weighted aggregation. Spec §6.1."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class ScoreWeights:
    consensus: float
    conviction: float
    continuity: float
    cloning_quality: float


def load_weights(path: Path) -> ScoreWeights:
    with path.open("rb") as f:
        data = tomllib.load(f)
    w = data["weights"]
    total = sum(w.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"weights sum must be ~1.0, got {total:.4f} from {path}")
    return ScoreWeights(
        consensus=float(w["consensus"]),
        conviction=float(w["conviction"]),
        continuity=float(w["continuity"]),
        cloning_quality=float(w["cloning_quality"]),
    )


def weighted_total(
    consensus_s: float,
    conviction_s: float,
    continuity_s: float,
    cloning_quality_s: float,
    weights: ScoreWeights,
) -> float:
    return (
        consensus_s * weights.consensus
        + conviction_s * weights.conviction
        + continuity_s * weights.continuity
        + cloning_quality_s * weights.cloning_quality
    )


def compute_total_scores(
    conn: duckdb.DuckDBPyConnection, weights: ScoreWeights, manager_count: int | None = None
) -> int:
    """consensus_quarterly + signals_quarterly + managers를 결합해 total_scores 적재.

    consensus_score = consensus_quarterly.holder_count / manager_count  (DRY: 이미 집계된 값 활용)
    conviction_score = signals_quarterly conviction 평균 (보유 거장)
    continuity_score = signals_quarterly continuity 평균
    cloning_quality_score = managers.cloning_score_weight 단순 평균 (보유 거장만)
    """
    # manager_count를 호출자가 지정하지 않으면 DB에서 동적 derive
    if manager_count is None:
        manager_count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0] or 1

    conn.execute("DELETE FROM total_scores")
    conn.execute(
        """
        INSERT INTO total_scores
        WITH agg AS (
            SELECT s.period_of_report, s.cusip,
                   AVG(s.conviction_score) AS conviction_s,
                   AVG(s.continuity_score) AS continuity_s,
                   AVG(m.cloning_score_weight) AS cloning_quality_s
            FROM signals_quarterly s
            JOIN managers m ON s.cik = m.cik
            WHERE s.change_type != 'exit'
            GROUP BY s.period_of_report, s.cusip
        )
        SELECT a.period_of_report, a.cusip,
               cm.ticker,
               (c.holder_count * 1.0 / ?) AS consensus_score,
               a.conviction_s,
               a.continuity_s,
               a.cloning_quality_s,
               (c.holder_count * 1.0 / ?) * ?
               + COALESCE(a.conviction_s, 0) * ?
               + COALESCE(a.continuity_s, 0) * ?
               + COALESCE(a.cloning_quality_s, 0) * ? AS total_score
        FROM agg a
        JOIN consensus_quarterly c
          ON c.period_of_report = a.period_of_report AND c.cusip = a.cusip
        LEFT JOIN cusip_ticker_map cm ON a.cusip = cm.cusip
        """,
        (
            manager_count, manager_count,
            weights.consensus, weights.conviction,
            weights.continuity, weights.cloning_quality,
        ),
    )
    return conn.execute("SELECT COUNT(*) FROM total_scores").fetchone()[0]

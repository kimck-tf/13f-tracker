"""Conviction score per holding (within manager portfolio). Spec §6.1."""
from __future__ import annotations

import duckdb


def conviction_score(weight_pct: float, top_weight: float, holding_count: int) -> float:
    if top_weight <= 0:
        return 0.0
    if holding_count == 1:
        return 1.0
    return min(1.0, weight_pct / top_weight)


def update_conviction_scores(conn: duckdb.DuckDBPyConnection) -> int:
    """signals_quarterly에 conviction_score 채워넣기.

    포트폴리오 단위로 top_weight 계산 후 각 종목 weight / top_weight.
    """
    conn.execute(
        """
        WITH top_per_portfolio AS (
            SELECT cik, period_of_report, MAX(weight_pct) AS top_w,
                   COUNT(*) AS holding_n
            FROM signals_quarterly
            GROUP BY cik, period_of_report
        )
        UPDATE signals_quarterly s
        SET conviction_score = CASE
            WHEN tp.top_w <= 0 THEN 0
            WHEN tp.holding_n = 1 THEN 1.0
            ELSE LEAST(1.0, s.weight_pct / tp.top_w)
        END
        FROM top_per_portfolio tp
        WHERE s.cik = tp.cik AND s.period_of_report = tp.period_of_report
        """
    )
    return conn.execute(
        "SELECT COUNT(*) FROM signals_quarterly WHERE conviction_score IS NOT NULL"
    ).fetchone()[0]

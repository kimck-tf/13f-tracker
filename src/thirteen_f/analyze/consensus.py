"""Consensus aggregation per (period, cusip). Spec §6.2."""
from __future__ import annotations

import duckdb


def compute_consensus(conn: duckdb.DuckDBPyConnection) -> int:
    conn.execute("DELETE FROM consensus_quarterly")
    conn.execute(
        """
        INSERT INTO consensus_quarterly
        SELECT
            s.period_of_report,
            s.cusip,
            ANY_VALUE(m.ticker) AS ticker,
            COUNT(DISTINCT s.cik) AS holder_count,
            SUM(CASE WHEN s.change_type = 'new' THEN 1 ELSE 0 END) AS new_buy_count,
            STRING_AGG(DISTINCT s.cik, ',' ORDER BY s.cik) AS holder_ciks,
            AVG(s.conviction_score) AS avg_conviction
        FROM signals_quarterly s
        LEFT JOIN cusip_ticker_map m ON s.cusip = m.cusip
        WHERE s.change_type != 'exit'   -- 청산한 거장은 holder에서 제외
        GROUP BY s.period_of_report, s.cusip
        """
    )
    return conn.execute("SELECT COUNT(*) FROM consensus_quarterly").fetchone()[0]

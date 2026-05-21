"""ConsensusTopK: holder_count >= min_holders 중 total_score 상위 K개."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class ConsensusTopK(Strategy):
    def __init__(self, min_holders: int = 3, top_k: int = 20) -> None:
        self.min_holders = min_holders
        self.top_k = top_k
        self.name = f"ConsensusTopK({min_holders},{top_k})"

    def params_json(self) -> str:
        return json.dumps({"min_holders": self.min_holders, "top_k": self.top_k})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        latest_period = conn.execute(
            """
            SELECT MAX(t.period_of_report)
            FROM total_scores t
            WHERE EXISTS (
                SELECT 1 FROM filings f
                WHERE f.period_of_report = t.period_of_report
                  AND f.filed_at <= ?
            )
            """,
            (as_of_date,),
        ).fetchone()[0]
        if latest_period is None:
            return {}
        rows = conn.execute(
            """
            SELECT t.ticker
            FROM total_scores t
            JOIN consensus_quarterly c
              ON c.period_of_report = t.period_of_report AND c.cusip = t.cusip
            WHERE t.period_of_report = ?
              AND c.holder_count >= ?
              AND t.ticker IS NOT NULL
            ORDER BY t.total_score DESC NULLS LAST
            LIMIT ?
            """,
            (latest_period, self.min_holders, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        w = 1.0 / len(rows)
        return {r[0]: w for r in rows}

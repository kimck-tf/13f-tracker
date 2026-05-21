"""NewBuyOnly: 신규 매수 컨센서스만 추종."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class NewBuyOnly(Strategy):
    def __init__(self, min_holders: int = 2, top_k: int = 15) -> None:
        self.min_holders = min_holders
        self.top_k = top_k
        self.name = f"NewBuyOnly({min_holders},{top_k})"

    def params_json(self) -> str:
        return json.dumps({"min_holders": self.min_holders, "top_k": self.top_k})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        latest_period = conn.execute(
            """
            SELECT MAX(c.period_of_report)
            FROM consensus_quarterly c
            WHERE EXISTS (
                SELECT 1 FROM filings f
                WHERE f.period_of_report = c.period_of_report AND f.filed_at <= ?
            )
            """,
            (as_of_date,),
        ).fetchone()[0]
        if latest_period is None:
            return {}
        rows = conn.execute(
            """
            SELECT c.ticker
            FROM consensus_quarterly c
            JOIN total_scores t
              ON t.period_of_report = c.period_of_report AND t.cusip = c.cusip
            WHERE c.period_of_report = ?
              AND c.new_buy_count >= ?
              AND c.ticker IS NOT NULL
            ORDER BY t.total_score DESC NULLS LAST
            LIMIT ?
            """,
            (latest_period, self.min_holders, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        w = 1.0 / len(rows)
        return {r[0]: w for r in rows}

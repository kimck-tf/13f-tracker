"""ScoreTopK: total_score 상위 K개 종목 동일 가중."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class ScoreTopK(Strategy):
    def __init__(self, top_k: int = 20) -> None:
        self.top_k = top_k
        self.name = f"ScoreTopK({top_k})"

    def params_json(self) -> str:
        return json.dumps({"top_k": self.top_k})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        # as_of_date에 알려진 최신 분기 (filings.filed_at <= as_of_date)
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
            SELECT ticker
            FROM total_scores
            WHERE period_of_report = ?
              AND ticker IS NOT NULL
            ORDER BY total_score DESC NULLS LAST
            LIMIT ?
            """,
            (latest_period, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        w = 1.0 / len(rows)
        return {r[0]: w for r in rows}

"""ScoreTopK: total_score 상위 K개 종목 동일 가중."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy, latest_public_period


class ScoreTopK(Strategy):
    def __init__(self, top_k: int = 20) -> None:
        self.top_k = top_k
        self.name = f"ScoreTopK({top_k})"

    def params_json(self) -> str:
        return json.dumps({"top_k": self.top_k})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        # as_of_date에 매니저 전원의 13F-HR이 공개된 최신 분기
        latest_period = latest_public_period(conn, as_of_date, "total_scores")
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

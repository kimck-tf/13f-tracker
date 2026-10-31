"""ConsensusTopK: holder_count >= min_holders 중 total_score 상위 K개."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy, latest_public_period


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
        latest_period = latest_public_period(conn, as_of_date, "total_scores")
        if latest_period is None:
            return {}
        rows = conn.execute(
            """
            WITH cand AS (
                SELECT t.ticker, t.total_score, c.holder_count,
                       SUBSTR(t.cusip, 1, 6) AS issuer
                FROM total_scores t
                JOIN consensus_quarterly c
                  ON c.period_of_report = t.period_of_report AND c.cusip = t.cusip
                LEFT JOIN cusip_ticker_map m ON m.cusip = t.cusip
                WHERE t.period_of_report = ?
                  AND t.ticker IS NOT NULL
                  AND COALESCE(m.is_etf, FALSE) = FALSE
            ),
            one_per_issuer AS (
                -- 발행사(CUSIP 앞 6자리)당 total_score 최고 클래스 하나.
                -- 보유자 수는 클래스 중 최대값으로 본다
                SELECT ticker, total_score,
                       MAX(holder_count) OVER (PARTITION BY issuer) AS issuer_holders
                FROM cand
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY issuer ORDER BY total_score DESC NULLS LAST, ticker
                ) = 1
            )
            SELECT ticker
            FROM one_per_issuer
            WHERE issuer_holders >= ?
            ORDER BY total_score DESC NULLS LAST
            LIMIT ?
            """,
            (latest_period, self.min_holders, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        w = 1.0 / len(rows)
        return {r[0]: w for r in rows}

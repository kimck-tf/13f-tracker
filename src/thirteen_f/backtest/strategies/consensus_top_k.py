"""ConsensusTopK: holder_count >= min_holders 중 total_score 상위 K개."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import (
    ISSUER_CLASS_CANDIDATES_SQL,
    ISSUER_CLASS_ORDER_SQL,
    NON_COMMON_CUSIPS_SQL,
    Strategy,
    latest_public_period,
)


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
            f"""
            WITH cand AS (
                SELECT t.ticker, t.total_score, t.held_since, t.score_then, c.holder_count,
                       SUBSTR(t.cusip, 1, 6) AS issuer, nc.cusip IS NOT NULL AS non_common
                FROM ({ISSUER_CLASS_CANDIDATES_SQL}) t
                JOIN consensus_quarterly c
                  ON c.period_of_report = t.period_of_report AND c.cusip = t.cusip
                LEFT JOIN ({NON_COMMON_CUSIPS_SQL}) nc ON nc.cusip = t.cusip
            ),
            one_per_issuer AS (
                -- 발행사(CUSIP 앞 6자리)당 한 클래스 (ISSUER_CLASS_ORDER_SQL). 순위에 쓰는 점수는
                -- 대표 클래스와 무관하게 보통주 클래스 중 최고 total_score, 보유자 수는 클래스 중
                -- 최대값으로 본다
                SELECT ticker,
                       FIRST_VALUE(total_score) OVER (
                           PARTITION BY issuer
                           ORDER BY non_common, total_score DESC NULLS LAST, ticker
                       ) AS issuer_score,
                       MAX(holder_count) OVER (PARTITION BY issuer) AS issuer_holders
                FROM cand
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY issuer ORDER BY {ISSUER_CLASS_ORDER_SQL}
                ) = 1
            )
            SELECT ticker
            FROM one_per_issuer
            WHERE issuer_holders >= ?
            ORDER BY issuer_score DESC NULLS LAST
            LIMIT ?
            """,
            (latest_period, latest_period, self.min_holders, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        w = 1.0 / len(rows)
        return {r[0]: w for r in rows}

"""ConvictionFollow: 거장별 conviction Top-N의 통합."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class ConvictionFollow(Strategy):
    def __init__(self, top_k: int = 10) -> None:
        self.top_k = top_k  # 거장별 Top-K conviction 종목
        self.name = f"ConvictionFollow({top_k})"

    def params_json(self) -> str:
        return json.dumps({"top_k": self.top_k})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        # 각 거장의 최신 분기에서 conviction 상위 K개 종목 수집
        rows = conn.execute(
            """
            WITH latest_per_cik AS (
                SELECT cik, MAX(period_of_report) AS p
                FROM signals_quarterly s
                WHERE EXISTS (
                    SELECT 1 FROM filings f
                    WHERE f.cik = s.cik AND f.period_of_report = s.period_of_report
                      AND f.filed_at <= ?
                )
                GROUP BY cik
            ),
            ranked AS (
                SELECT s.cik, s.cusip, s.conviction_score,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.cik ORDER BY s.conviction_score DESC NULLS LAST
                       ) AS rn
                FROM signals_quarterly s
                JOIN latest_per_cik l ON s.cik = l.cik AND s.period_of_report = l.p
                WHERE s.change_type != 'exit'
            )
            SELECT r.cusip, m.ticker, r.conviction_score
            FROM ranked r
            LEFT JOIN cusip_ticker_map m ON r.cusip = m.cusip
            WHERE r.rn <= ? AND m.ticker IS NOT NULL
            """,
            (as_of_date, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        # 동일 ticker가 여러 거장에게 등장 → 빈도(또는 conviction 합)로 가중
        weight_sum: dict[str, float] = defaultdict(float)
        for _cusip, ticker, conviction in rows:
            weight_sum[ticker] += float(conviction or 0)
        total = sum(weight_sum.values())
        if total <= 0:
            return {}
        return {t: w / total for t, w in weight_sum.items()}

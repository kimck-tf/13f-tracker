"""ConvictionFollow: 거장별 conviction Top-N의 통합."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import NON_COMMON_CUSIPS_SQL, Strategy


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
            f"""
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
            cand AS (
                -- ETF를 빼고, 거장마다 발행사(CUSIP 앞 6자리)당 한 클래스. 매핑된 클래스를 먼저
                -- (순위 뒤에 걸러질 미매핑 형제가 밀어내지 않게), 그다음 보통주(워런트·권리는
                -- 뒤로), 그다음 conviction
                SELECT s.cik, SUBSTR(s.cusip, 1, 6) AS issuer, m.ticker,
                       nc.cusip IS NOT NULL AS non_common, s.conviction_score
                FROM signals_quarterly s
                JOIN latest_per_cik l ON s.cik = l.cik AND s.period_of_report = l.p
                LEFT JOIN cusip_ticker_map m ON m.cusip = s.cusip
                LEFT JOIN ({NON_COMMON_CUSIPS_SQL}) nc ON nc.cusip = s.cusip
                WHERE s.change_type != 'exit'
                  AND COALESCE(m.is_etf, FALSE) = FALSE
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY s.cik, SUBSTR(s.cusip, 1, 6)
                    ORDER BY m.ticker IS NULL, nc.cusip IS NOT NULL,
                             s.conviction_score DESC NULLS LAST, s.cusip
                ) = 1
            ),
            ranked AS (
                SELECT issuer, ticker, non_common, conviction_score,
                       ROW_NUMBER() OVER (
                           PARTITION BY cik ORDER BY conviction_score DESC NULLS LAST
                       ) AS rn
                FROM cand
            ),
            by_ticker AS (
                SELECT issuer, ticker, BOOL_OR(non_common) AS non_common,
                       SUM(conviction_score) AS w
                FROM ranked
                WHERE rn <= ? AND ticker IS NOT NULL
                GROUP BY issuer, ticker
            )
            -- 거장마다 고른 클래스가 달라도(GOOG·GOOGL) 포트폴리오에는 발행사당 한 클래스:
            -- 보통주 먼저, 그다음 conviction 합이 큰 클래스. 비중은 발행사의 conviction 합
            SELECT FIRST(ticker ORDER BY non_common, w DESC, ticker), SUM(w)
            FROM by_ticker
            GROUP BY issuer
            """,
            (as_of_date, self.top_k),
        ).fetchall()
        if not rows:
            return {}
        weight_sum = {ticker: float(w or 0) for ticker, w in rows}
        total = sum(weight_sum.values())
        if total <= 0:
            return {}
        return {t: w / total for t, w in weight_sum.items()}

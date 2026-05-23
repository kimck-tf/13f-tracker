"""MultiManager: 여러 매니저의 ``latest 13F`` holdings를 집계해 top_k 종목 선정.

Plan §D1 보강: SingleManagerClone과 동일한 lookahead-safe 패턴
(``filed_at <= as_of_date`` + ``superseded_by IS NULL`` + 13F-HR only).
DuckDB ``QUALIFY ROW_NUMBER()``로 매니저별 ``latest accession_no``까지 식별 —
같은 (cik, period_of_report)에 정정본이 여러 건 있어도 가장 최신 1건만 사용.
"""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class MultiManager(Strategy):
    """Aggregate top holdings from multiple managers (lookahead-safe).

    Each manager contributes their latest 13F-HR (as of ``as_of_date``).
    Holdings are summed by ticker (across managers), sorted by total USD value,
    and the top ``top_k`` tickers form the equal-weight (or by-value) portfolio.
    Manager periods may differ — that's intentional (each uses their freshest data).

    ⚠️ ``weighting="byvalue"`` stale-period bias:
      매니저별 분기가 다를 때, value_usd가 stale period의 가격으로 산정된 값이라
      비교하기에 균질하지 않음. 예: A는 Q1 filing(가치 100B at Q1 가격), B는 Q2 filing
      (80B at Q2 가격)일 때, A의 가중치가 인공적으로 커질 수 있음. ``"equal"``이
      이런 bias로부터 자유로움 — 비교 신뢰성이 중요하면 equal 권장.
    """

    def __init__(
        self,
        mgr_labels: list[str],
        top_k: int = 15,
        weighting: str = "equal",  # "equal" | "byvalue"
    ) -> None:
        self.mgr_labels = list(mgr_labels)
        self.top_k = top_k
        self.weighting = weighting
        self.name = f"MultiManager({len(self.mgr_labels)} mgrs, top={top_k})"

    def params_json(self) -> str:
        return json.dumps({
            "mgr_labels": self.mgr_labels,
            "top_k": self.top_k,
            "weighting": self.weighting,
        })

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        if not self.mgr_labels:
            return {}
        placeholders = ",".join("?" for _ in self.mgr_labels)
        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT f.cik, f.accession_no
                FROM filings f
                JOIN managers mg ON mg.cik = f.cik
                WHERE mg.label IN ({placeholders})
                  AND f.filed_at <= ?
                  AND f.superseded_by IS NULL
                  AND f.form_type LIKE '13F-HR%'
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY f.cik
                    ORDER BY f.period_of_report DESC, f.filed_at DESC
                ) = 1
            )
            SELECT m.ticker, SUM(h.value_usd) AS total_value
            FROM holdings h
            JOIN latest l ON l.accession_no = h.accession_no
            JOIN cusip_ticker_map m ON m.cusip = h.cusip
            WHERE m.ticker IS NOT NULL
              AND h.value_usd > 0
            GROUP BY m.ticker
            ORDER BY total_value DESC
            LIMIT ?
            """,
            [*self.mgr_labels, as_of_date, self.top_k],
        ).fetchall()

        if not rows:
            return {}

        if self.weighting == "byvalue":
            total = sum(float(v) for _, v in rows)
            if total <= 0:
                return {}
            return {ticker: float(val) / total for ticker, val in rows}
        # equal-weight (default)
        n = len(rows)
        return {ticker: 1.0 / n for ticker, _ in rows}

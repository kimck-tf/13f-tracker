"""SingleManagerClone: 특정 거장 1명의 최신 13F를 비중 그대로 복제."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class SingleManagerClone(Strategy):
    def __init__(self, label: str) -> None:
        self.label = label
        self.name = f"SingleManagerClone({label})"

    def params_json(self) -> str:
        return json.dumps({"label": self.label})

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        # 1. 라벨 → CIK
        row = conn.execute(
            "SELECT cik FROM managers WHERE label = ?", (self.label,)
        ).fetchone()
        if not row:
            return {}
        cik = row[0]
        # 2. as_of_date 이전 최신 filing (superseded_by가 NULL인 것)
        latest = conn.execute(
            """
            SELECT accession_no FROM filings
            WHERE cik = ? AND filed_at <= ? AND superseded_by IS NULL
              AND form_type LIKE '13F-HR%'
            ORDER BY period_of_report DESC, filed_at DESC
            LIMIT 1
            """,
            (cik, as_of_date),
        ).fetchone()
        if not latest:
            return {}
        accession = latest[0]
        # 3. holdings + ticker 매핑 (ticker NULL 제외)
        rows = conn.execute(
            """
            SELECT m.ticker, h.value_usd
            FROM holdings h
            JOIN cusip_ticker_map m ON h.cusip = m.cusip
            WHERE h.accession_no = ?
              AND m.ticker IS NOT NULL
              AND h.value_usd > 0
            """,
            (accession,),
        ).fetchall()
        if not rows:
            return {}
        total = sum(r[1] for r in rows)
        if total <= 0:
            return {}
        return {ticker: value / total for ticker, value in rows}

"""Quarter-over-quarter change classification. Spec §6.1."""
from __future__ import annotations

from typing import Literal

import duckdb

ChangeType = Literal["new", "increase", "decrease", "exit", "hold"]


def classify_change(
    prev: int | None, curr: int | None, threshold: float = 0.05
) -> ChangeType:
    """단일 종목의 분기간 변화 분류."""
    if (prev is None or prev == 0) and curr and curr > 0:
        return "new"
    if prev and prev > 0 and (curr is None or curr == 0):
        return "exit"
    if prev is None or curr is None:
        # 둘 다 0 또는 None
        return "hold"
    delta = (curr - prev) / prev if prev > 0 else 0
    if delta > threshold:
        return "increase"
    if delta < -threshold:
        return "decrease"
    return "hold"


def compute_signals_quarterly(
    conn: duckdb.DuckDBPyConnection, threshold: float = 0.05
) -> int:
    """holdings 테이블에서 거장×CUSIP×분기 단위 변화 시그널 계산 후 signals_quarterly 적재.

    weight_pct = value_usd / 거장의 분기 총 가치.
    change_type, shares_change, value_change_usd 계산.
    Returns rows inserted.
    """
    conn.execute("DELETE FROM signals_quarterly")
    # 최신 정정본만 사용 (superseded_by IS NULL)
    conn.execute(
        """
        INSERT INTO signals_quarterly
        WITH effective AS (
            SELECT h.accession_no, f.cik, f.period_of_report, h.cusip,
                   h.shares, h.value_usd
            FROM holdings h
            JOIN filings f ON h.accession_no = f.accession_no
            WHERE f.superseded_by IS NULL
        ),
        agg_per_filing AS (
            -- 같은 (filing, cusip)의 옵션/일반주가 여러 줄일 수 있으므로 합산
            SELECT cik, period_of_report, cusip,
                   SUM(shares) AS shares,
                   SUM(value_usd) AS value_usd
            FROM effective
            GROUP BY cik, period_of_report, cusip
        ),
        portfolio_total AS (
            SELECT cik, period_of_report, SUM(value_usd) AS total_value
            FROM agg_per_filing
            GROUP BY cik, period_of_report
        ),
        lagged AS (
            SELECT a.cik, a.period_of_report, a.cusip, a.shares, a.value_usd,
                   p.total_value,
                   LAG(a.shares) OVER (
                       PARTITION BY a.cik, a.cusip ORDER BY a.period_of_report
                   ) AS prev_shares,
                   LAG(a.value_usd) OVER (
                       PARTITION BY a.cik, a.cusip ORDER BY a.period_of_report
                   ) AS prev_value
            FROM agg_per_filing a
            JOIN portfolio_total p USING (cik, period_of_report)
        )
        SELECT cik, cusip, period_of_report,
               CASE
                  WHEN (prev_shares IS NULL OR prev_shares = 0) AND shares > 0 THEN 'new'
                  WHEN prev_shares > 0 AND (shares IS NULL OR shares = 0) THEN 'exit'
                  WHEN prev_shares IS NULL OR prev_shares = 0 THEN 'hold'
                  WHEN (shares - prev_shares) * 1.0 / prev_shares > ? THEN 'increase'
                  WHEN (shares - prev_shares) * 1.0 / prev_shares < -? THEN 'decrease'
                  ELSE 'hold'
               END AS change_type,
               (shares - COALESCE(prev_shares, 0)) AS shares_change,
               (value_usd - COALESCE(prev_value, 0)) AS value_change_usd,
               CASE WHEN total_value > 0 THEN value_usd * 1.0 / total_value ELSE 0 END AS weight_pct,
               NULL::DOUBLE AS conviction_score,
               NULL::DOUBLE AS continuity_score
        FROM lagged
        """,
        (threshold, threshold),
    )
    return conn.execute("SELECT COUNT(*) FROM signals_quarterly").fetchone()[0]

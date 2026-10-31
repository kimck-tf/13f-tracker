"""금액을 천 달러 단위로 보고한 필링 찾기·보정. Spec §5.3.

2023-01-03 이후 필링은 달러로 보고해야 하지만 일부 필러(Baupost·Duquesne 등)는 여전히 천 달러로
낸다. 필링마다 `value_usd / (shares × 분기말 종가)`의 중앙값을 보고 1/1000 수준이면 ×1000 한다.
"""
from __future__ import annotations

import duckdb

RATIO_THRESHOLD = 0.01  # 정상 필링의 중앙값은 ~1, 천 달러 단위 필링은 ~0.001
MIN_ROWS = 5            # 비교 가능한 행이 이보다 적으면 판정하지 않는다


def detect_thousand_unit_filings(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """천 달러 단위로 보고된 것으로 보이는 유효 필링의 accession_no (정렬).

    옵션(put_call ≠ '')·0주·0달러·ticker 미매핑 행과 분기말 이전 10일 안에 종가가 없는 행은 뺀다.
    """
    rows = conn.execute(
        """
        WITH periods AS (
            SELECT DISTINCT period_of_report FROM filings
        ),
        period_close AS (
            -- 분기말 이하 마지막 종가. 행마다 상관 서브쿼리를 쓰지 않도록
            -- 분기 × 가격을 한 번에 조인한다
            SELECT p.period_of_report, pr.ticker, MAX_BY(pr.close, pr.date) AS close
            FROM periods p
            JOIN prices pr
              ON pr.date <= p.period_of_report
             AND pr.date > p.period_of_report - INTERVAL 10 DAY
            WHERE pr.close > 0
            GROUP BY p.period_of_report, pr.ticker
        ),
        ratios AS (
            SELECT h.accession_no, h.value_usd / (h.shares * pc.close) AS ratio
            FROM holdings h
            JOIN filings f ON f.accession_no = h.accession_no AND f.superseded_by IS NULL
            JOIN cusip_ticker_map m ON m.cusip = h.cusip AND m.ticker IS NOT NULL
            JOIN period_close pc
              ON pc.period_of_report = f.period_of_report AND pc.ticker = m.ticker
            WHERE h.put_call = '' AND h.shares > 0 AND h.value_usd > 0
        )
        SELECT accession_no
        FROM ratios
        GROUP BY accession_no
        HAVING COUNT(*) >= ? AND MEDIAN(ratio) < ?
        ORDER BY accession_no
        """,
        (MIN_ROWS, RATIO_THRESHOLD),
    ).fetchall()
    return [r[0] for r in rows]


def fix_thousand_unit_filings(conn: duckdb.DuckDBPyConnection) -> list[str]:
    """감지된 필링의 holdings.value_usd를 ×1000 하고 그 accession_no를 돌려준다.

    보정 뒤에는 비율이 ~1이 되어 다시 감지되지 않으므로 여러 번 실행해도 한 번만 곱해진다.
    """
    accessions = detect_thousand_unit_filings(conn)
    for acc in accessions:
        conn.execute(
            "UPDATE holdings SET value_usd = value_usd * 1000 WHERE accession_no = ?", (acc,)
        )
    return accessions

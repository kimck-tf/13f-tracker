"""Continuity score: 끊기지 않은 매집 시퀀스 길이 / 4. Spec §6.1."""
from __future__ import annotations

import duckdb

WINDOW = 4


def continuity_from_changes(history: list[str]) -> float:
    """history는 오래된 → 최신 순서. decrease/exit를 만나면 reset.

    Returns: count of unbroken buying-quarters ending at the latest, capped at WINDOW,
    divided by WINDOW.
    """
    count = 0
    for ch in history[-WINDOW:]:
        if ch in ("decrease", "exit"):
            count = 0  # reset
            continue
        if ch in ("new", "increase", "hold"):
            count += 1
        else:
            count = 0
    return min(count, WINDOW) / WINDOW


def update_continuity_scores(conn: duckdb.DuckDBPyConnection) -> int:
    """signals_quarterly에 continuity_score 채워넣기.

    (cik, cusip)별 시간순으로 현재 행과 직전 3개 행의 change_type을 LAG로 읽어, 끝에서부터
    decrease/exit 없이 이어진 분기 수 ÷ WINDOW를 한 번의 UPDATE로 쓴다.
    `continuity_from_changes`와 같은 값이다 (테스트가 둘을 비교한다).
    """
    conn.execute(
        """
        UPDATE signals_quarterly s
        SET continuity_score = w.score
        FROM (
            SELECT cik, cusip, period_of_report,
                   (CASE WHEN c0 IN ('decrease', 'exit') THEN 0
                         WHEN c1 IS NULL OR c1 IN ('decrease', 'exit') THEN 1
                         WHEN c2 IS NULL OR c2 IN ('decrease', 'exit') THEN 2
                         WHEN c3 IS NULL OR c3 IN ('decrease', 'exit') THEN 3
                         ELSE 4 END) / 4.0 AS score
            FROM (
                SELECT cik, cusip, period_of_report, change_type AS c0,
                       LAG(change_type, 1) OVER w AS c1,
                       LAG(change_type, 2) OVER w AS c2,
                       LAG(change_type, 3) OVER w AS c3
                FROM signals_quarterly
                WINDOW w AS (PARTITION BY cik, cusip ORDER BY period_of_report)
            )
        ) w
        WHERE s.cik = w.cik AND s.cusip = w.cusip AND s.period_of_report = w.period_of_report
        """
    )
    row = conn.execute("SELECT COUNT(*) FROM signals_quarterly").fetchone()
    return int(row[0]) if row else 0

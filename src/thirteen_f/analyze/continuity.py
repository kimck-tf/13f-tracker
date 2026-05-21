"""Continuity score: 끊기지 않은 매집 시퀀스 길이 / 4. Spec §6.1."""
from __future__ import annotations

import duckdb

WINDOW = 4


def continuity_from_changes(history: list[str]) -> float:
    """history는 오래된 → 최신 순서. decrease/exit를 만나면 reset.

    Returns: count of unbroken buying-quarters ending at the latest, capped at WINDOW, divided by WINDOW.
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

    각 (cik, cusip)에 대해 시간순 change_type 시퀀스를 만들고
    매 분기마다 직전 4분기 시퀀스로 score 계산.
    """
    rows = conn.execute(
        """
        SELECT cik, cusip, period_of_report, change_type
        FROM signals_quarterly
        ORDER BY cik, cusip, period_of_report
        """
    ).fetchall()

    # 그룹별 시퀀스 누적
    updates: list[tuple[float, str, str, object]] = []
    current_key: tuple[str, str] | None = None
    history: list[str] = []
    for cik, cusip, period, ch in rows:
        key = (cik, cusip)
        if key != current_key:
            current_key = key
            history = []
        history.append(ch)
        score = continuity_from_changes(history)
        updates.append((score, cik, cusip, period))

    conn.executemany(
        """
        UPDATE signals_quarterly
        SET continuity_score = ?
        WHERE cik = ? AND cusip = ? AND period_of_report = ?
        """,
        updates,
    )
    return len(updates)

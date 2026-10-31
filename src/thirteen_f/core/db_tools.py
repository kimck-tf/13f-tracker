"""DuckDB 파일 자체를 다루는 유틸 (단계 함수가 아닌 CLI 보조용)."""
from __future__ import annotations

from pathlib import Path

import duckdb

from thirteen_f.core.dates import quarter_label


def db_start_quarter(db_path: Path) -> str | None:
    """DB에 적재된 가장 이른 분기 (`filings.period_of_report` 최소값, 예: '2024Q1').

    파일이 없거나 filings가 비어 있으면 None. read-only로 연다.
    """
    if not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute("SELECT MIN(period_of_report) FROM filings").fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        return None
    return quarter_label(row[0])

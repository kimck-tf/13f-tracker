"""Quarto chapters에서 공통 사용하는 DuckDB 헬퍼.

Spec §3.1.1: pip install -e . 후 `from thirteen_f...` import 가능.
Quarter는 환경변수 THIRTEEN_F_QUARTER로 전달 (cli.py report 명령이 설정).
"""
from __future__ import annotations

import os
from datetime import date

import duckdb

from thirteen_f.core.config import load_settings


def get_conn() -> duckdb.DuckDBPyConnection:
    settings = load_settings()
    return duckdb.connect(str(settings.duckdb_path), read_only=True)


def get_quarter_arg() -> str:
    """환경변수 THIRTEEN_F_QUARTER 읽기 (기본 'latest')."""
    return os.environ.get("THIRTEEN_F_QUARTER", "latest")


def resolve_quarter(conn: duckdb.DuckDBPyConnection, quarter_arg: str | None = None) -> date:
    """quarter_arg: '2026Q1', 'latest', 또는 None(환경변수 사용)."""
    if quarter_arg is None:
        quarter_arg = get_quarter_arg()
    if quarter_arg == "latest":
        row = conn.execute(
            "SELECT MAX(period_of_report) FROM total_scores"
        ).fetchone()
        if not row or not row[0]:
            raise ValueError("DB에 total_scores 데이터가 없습니다.")
        return row[0]
    from thirteen_f.core.dates import quarter_end
    return quarter_end(quarter_arg)

"""DuckDB 파일 자체를 다루는 유틸 (단계 함수가 아닌 CLI 보조용)."""
from __future__ import annotations

import os
import shutil
from datetime import date, datetime
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


def first_public_date(db_path: Path) -> date | None:
    """DB에 든 13F-HR 가운데 가장 이른 제출일 — 그 전에는 어느 전략도 쓸 신호가 없다.

    파일이 없거나 13F-HR이 없으면 None. read-only로 연다.
    """
    if not db_path.exists():
        return None
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT MIN(filed_at) FROM filings WHERE form_type LIKE '13F-HR%'"
        ).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def backup_db(db_path: Path, keep: int = 3) -> Path | None:
    """DB 파일을 `backups/<stem>-YYYYMMDD-HHMMSS<suffix>`로 복사하고 최신 `keep`개만 남긴다.

    `backups/`는 Google Drive 동기화 폴더라, 동기화되지 않는 `db_path.parent`에 임시 이름으로
    먼저 복사한 뒤 옮긴다 (Drive가 쓰는 중인 파일을 올리지 않게). 파일이 없으면 None.
    """
    if not db_path.exists():
        return None
    bdir = db_path.parent / "backups"
    bdir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    final = bdir / f"{db_path.stem}-{stamp}{db_path.suffix}"
    partial = db_path.parent / f".{final.name}.partial"
    shutil.copy2(db_path, partial)
    os.replace(partial, final)
    backups = sorted(bdir.glob(f"{db_path.stem}-????????-??????{db_path.suffix}"))
    for old in backups[:-keep]:
        old.unlink()
    return final

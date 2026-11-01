import re
from datetime import date
from pathlib import Path

import duckdb

from scripts.init_db import init_db
from thirteen_f.core.db_tools import backup_db, db_start_quarter


def _db(tmp_path: Path, periods: list[date]) -> Path:
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    for i, p in enumerate(periods):
        c.execute(
            "INSERT INTO filings VALUES (?, 'c1', '13F-HR', ?, ?, FALSE, NULL)", (f"a{i}", p, p)
        )
    c.close()
    return db


def test_db_start_quarter_is_the_earliest_filing_quarter(tmp_path):
    db = _db(tmp_path, [date(2024, 6, 30), date(2024, 3, 31), date(2025, 3, 31)])
    assert db_start_quarter(db) == "2024Q1"


def test_db_start_quarter_is_none_for_empty_or_missing_db(tmp_path):
    assert db_start_quarter(_db(tmp_path, [])) is None
    assert db_start_quarter(tmp_path / "nope.duckdb") is None


def test_backup_db_copies_file_with_timestamp_name(tmp_path):
    db = tmp_path / "13f.duckdb"
    db.write_bytes(b"duck")
    out = backup_db(db)
    assert out is not None and out.parent == tmp_path / "backups"
    assert re.fullmatch(r"13f-\d{8}-\d{6}\.duckdb", out.name)
    assert out.read_bytes() == b"duck"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".partial")] == []


def test_backup_db_keeps_only_the_newest_three(tmp_path):
    db = tmp_path / "13f.duckdb"
    db.write_bytes(b"duck")
    bdir = tmp_path / "backups"
    bdir.mkdir()
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (bdir / f"13f-{stamp}.duckdb").write_bytes(b"old")
    backup_db(db, keep=3)
    names = sorted(p.name for p in bdir.iterdir())
    assert len(names) == 3 and "13f-20260101-000000.duckdb" not in names


def test_backup_db_returns_none_when_db_missing(tmp_path):
    assert backup_db(tmp_path / "none.duckdb") is None

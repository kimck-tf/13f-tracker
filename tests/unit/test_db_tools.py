from datetime import date
from pathlib import Path

import duckdb

from scripts.init_db import init_db
from thirteen_f.core.db_tools import db_start_quarter


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

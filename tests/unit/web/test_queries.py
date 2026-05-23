"""Smoke tests for web/queries.py — verify migrated SQL helpers work against DuckDB."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import upsert_filing, upsert_manager
from thirteen_f.web.queries import (
    latest_period,
    manager_list,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {
        "cik": "0000000001",
        "name": "Warren Buffett",
        "label": "buffett",
        "fund": "Berkshire Hathaway",
        "style": "value",
        "active_since": 1996,
        "cloning_score_weight": 1.0,
    })
    upsert_filing(c, {
        "accession_no": "a1",
        "cik": "0000000001",
        "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    yield c
    c.close()


def test_latest_period_returns_date(conn):
    p = latest_period(conn)
    assert isinstance(p, date)
    assert p == date(2024, 3, 31)


def test_latest_period_returns_none_for_empty(tmp_path):
    db = tmp_path / "empty.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    try:
        assert latest_period(c) is None
    finally:
        c.close()


def test_manager_list_returns_dataframe(conn):
    df = manager_list(conn)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["label"] == "buffett"
    assert row["name"] == "Warren Buffett"
    assert row["style"] == "value"

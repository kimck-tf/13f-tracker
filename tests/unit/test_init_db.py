from pathlib import Path

import duckdb
import pytest

from scripts.init_db import init_db, EXPECTED_TABLES


def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()
    assert tables == EXPECTED_TABLES


def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    init_db(db_path)  # 두 번 호출해도 에러 X
    conn = duckdb.connect(str(db_path), read_only=True)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()
    assert tables == EXPECTED_TABLES


def test_holdings_pk_no_null(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES ('0000000001','Test','t','Fund','value',2020,1.0)"
    )
    conn.execute(
        "INSERT INTO filings VALUES "
        "('acc1','0000000001','13F-HR',DATE '2024-03-31',DATE '2024-05-15',FALSE,NULL)"
    )
    # put_call DEFAULT '' 검증: NULL 대신 '' 저장
    conn.execute(
        "INSERT INTO holdings (accession_no, cusip, value_usd, shares) "
        "VALUES ('acc1','123456789',1000,10)"
    )
    row = conn.execute(
        "SELECT put_call, title_of_class FROM holdings WHERE cusip='123456789'"
    ).fetchone()
    assert row == ("", "")
    conn.close()

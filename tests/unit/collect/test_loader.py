from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import (
    upsert_manager,
    upsert_filing,
    upsert_holdings,
    mark_supersedes,
    remove_filing,
)


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "test.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def test_upsert_manager_idempotent(conn):
    m = {"cik": "0000000001", "name": "Test", "label": "T", "fund": "Fund",
         "style": "value", "active_since": 2020, "cloning_score_weight": 1.0}
    upsert_manager(conn, m)
    upsert_manager(conn, m)  # 중복 호출 OK
    count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
    assert count == 1


def test_upsert_holdings_with_options(conn):
    upsert_manager(conn, {"cik": "0000000001", "name": "T", "label": "T", "fund": "F",
                          "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    upsert_filing(conn, {"accession_no": "acc1", "cik": "0000000001",
                         "form_type": "13F-HR", "period_of_report": date(2024, 3, 31),
                         "filed_at": date(2024, 5, 15), "is_amendment": False})
    upsert_holdings(conn, "acc1", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 500, "shares": 5, "share_type": "SH", "put_call": "Call"},
    ])
    rows = conn.execute("SELECT COUNT(*) FROM holdings WHERE accession_no='acc1'").fetchone()[0]
    assert rows == 2  # put_call로 구분


def test_upsert_holdings_aggregates_duplicate_keys(conn):
    """13F XML이 같은 (cusip, title_of_class, put_call) 조합을 voting authority별로
    분할 보고하는 경우 PK 위반이 나지 않도록 SUM 집계되어야 한다."""
    upsert_manager(conn, {"cik": "0000000001", "name": "T", "label": "T", "fund": "F",
                          "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    upsert_filing(conn, {"accession_no": "acc1", "cik": "0000000001",
                         "form_type": "13F-HR", "period_of_report": date(2024, 3, 31),
                         "filed_at": date(2024, 5, 15), "is_amendment": False})
    upsert_holdings(conn, "acc1", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 500, "shares": 5, "share_type": "SH", "put_call": ""},
    ])
    row = conn.execute(
        "SELECT shares, value_usd FROM holdings WHERE accession_no='acc1' AND cusip='037833100'"
    ).fetchone()
    assert row == (15, 1500)


def test_mark_supersedes_empty_filings_returns_zero(conn):
    """cik에 해당하는 filing이 0개일 때 executemany 빈 리스트 에러 없이 0 반환."""
    upsert_manager(conn, {"cik": "0000000099", "name": "T", "label": "T", "fund": "F",
                          "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    n = mark_supersedes(conn, "0000000099")
    assert n == 0


def test_mark_supersedes(conn):
    upsert_manager(conn, {"cik": "0000000001", "name": "T", "label": "T", "fund": "F",
                          "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    upsert_filing(conn, {"accession_no": "acc_v1", "cik": "0000000001",
                         "form_type": "13F-HR", "period_of_report": date(2024, 3, 31),
                         "filed_at": date(2024, 5, 15), "is_amendment": False})
    upsert_filing(conn, {"accession_no": "acc_v2", "cik": "0000000001",
                         "form_type": "13F-HR/A", "period_of_report": date(2024, 3, 31),
                         "filed_at": date(2024, 7, 10), "is_amendment": True})
    mark_supersedes(conn, "0000000001")
    row = conn.execute("SELECT superseded_by FROM filings WHERE accession_no='acc_v1'").fetchone()
    assert row[0] == "acc_v2"
    row2 = conn.execute("SELECT superseded_by FROM filings WHERE accession_no='acc_v2'").fetchone()
    assert row2[0] is None


def test_remove_filing_makes_original_valid_again(conn):
    """적재하지 않을 정정(NEW HOLDINGS)을 지우고 재계산하면 원본이 다시 유효본이 된다."""
    upsert_manager(conn, {"cik": "0000000001", "name": "T", "label": "T", "fund": "F",
                          "style": "value", "active_since": 2020, "cloning_score_weight": 1.0})
    upsert_filing(conn, {"accession_no": "orig", "cik": "0000000001",
                         "form_type": "13F-HR", "period_of_report": date(2025, 3, 31),
                         "filed_at": date(2025, 5, 15), "is_amendment": False})
    upsert_filing(conn, {"accession_no": "new_holdings", "cik": "0000000001",
                         "form_type": "13F-HR/A", "period_of_report": date(2025, 3, 31),
                         "filed_at": date(2025, 8, 14), "is_amendment": True})
    upsert_holdings(conn, "new_holdings", [
        {"cusip": "594918104", "name_of_issuer": "Microsoft", "title_of_class": "COM",
         "value_usd": 100, "shares": 1, "share_type": "SH", "put_call": ""},
    ])
    mark_supersedes(conn, "0000000001")

    remove_filing(conn, "new_holdings")
    mark_supersedes(conn, "0000000001")

    assert conn.execute(
        "SELECT superseded_by FROM filings WHERE accession_no='orig'"
    ).fetchone()[0] is None
    assert conn.execute(
        "SELECT COUNT(*) FROM filings WHERE accession_no='new_holdings'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM holdings WHERE accession_no='new_holdings'"
    ).fetchone()[0] == 0

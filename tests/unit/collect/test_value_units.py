from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager
from thirteen_f.collect.value_units import detect_thousand_unit_filings, fix_thousand_unit_filings

Q1 = date(2024, 3, 31)


def _rows(n, value, put_call=""):
    return [
        {
            "cusip": f"C{i:08d}",
            "name_of_issuer": f"C{i}",
            "title_of_class": "COM",
            "value_usd": value,
            "shares": 10,
            "share_type": "SH",
            "put_call": put_call,
        }
        for i in range(n)
    ]


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(
        c,
        {
            "cik": "m",
            "name": "M",
            "label": "M",
            "fund": "F",
            "style": "value",
            "active_since": 2020,
            "cloning_score_weight": 1.0,
        },
    )
    for acc in ("k1", "n1", "s1"):
        upsert_filing(
            c,
            {
                "accession_no": acc,
                "cik": "m",
                "form_type": "13F-HR",
                "period_of_report": Q1,
                "filed_at": date(2024, 5, 15),
                "is_amendment": False,
            },
        )
    for i in range(6):  # 티커 매핑 + 분기말 종가 100
        c.execute(
            "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)",
            (f"C{i:08d}", f"T{i}"),
        )
        c.execute(
            "INSERT INTO prices (ticker, date, close, adj_close) "
            "VALUES (?, DATE '2024-03-28', 100.0, 100.0)",
            (f"T{i}",),
        )
    upsert_holdings(
        c, "k1", _rows(6, value=1)
    )  # 10주 × $100 = $1,000인데 value 1 → 비율 0.001 (천 달러 단위)
    upsert_holdings(c, "n1", _rows(6, value=1000))  # 정상
    upsert_holdings(c, "s1", _rows(3, value=1))  # 3행뿐 → 판정 보류
    yield c
    c.close()


def test_detects_filings_reported_in_thousands(conn):
    assert detect_thousand_unit_filings(conn) == ["k1"]


def test_fix_multiplies_by_1000_once(conn):
    assert fix_thousand_unit_filings(conn) == ["k1"]
    assert (
        conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 'k1'").fetchone()[0]
        == 6000
    )
    assert (
        conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 'n1'").fetchone()[0]
        == 6000
    )
    assert (
        conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 's1'").fetchone()[0]
        == 3
    )
    assert fix_thousand_unit_filings(conn) == []  # 멱등


def test_option_rows_are_ignored_in_detection(conn):
    # upsert_holdings는 같은 accession의 기존 행을 지우고 다시 넣으므로 전체 목록을 준다.
    # 정상 5행(비율 1) + 풋 6행(비율 0.001): 풋을 세면 중앙값이 0.001이라 오탐, 빼면 1.0
    upsert_holdings(conn, "n1", _rows(5, value=1000) + _rows(6, value=1, put_call="PUT"))
    assert detect_thousand_unit_filings(conn) == ["k1"]

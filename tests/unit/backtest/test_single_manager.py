from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.single_manager import SingleManagerClone
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {"cik": "0000000001", "name": "Buffett", "label": "Buffett",
                       "fund": "BRK", "style": "value", "active_since": 1996,
                       "cloning_score_weight": 1.0})
    upsert_filing(c, {"accession_no": "a1", "cik": "0000000001",
                      "form_type": "13F-HR", "period_of_report": date(2024, 3, 31),
                      "filed_at": date(2024, 5, 15), "is_amendment": False})
    upsert_holdings(c, "a1", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 800, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "037833200", "name_of_issuer": "B", "title_of_class": "COM",
         "value_usd": 200, "shares": 5, "share_type": "SH", "put_call": ""},
    ])
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("037833100", "AAPL", False), ("037833200", "B", False)],
    )
    yield c
    c.close()


def test_target_positions_weights_sum_to_one(conn):
    s = SingleManagerClone(label="Buffett")
    targets = s.get_target_positions(as_of_date=date(2024, 6, 1), conn=conn)
    assert pytest.approx(sum(targets.values()), abs=1e-6) == 1.0


def test_weights_proportional(conn):
    s = SingleManagerClone(label="Buffett")
    targets = s.get_target_positions(as_of_date=date(2024, 6, 1), conn=conn)
    assert targets["AAPL"] == pytest.approx(0.8)
    assert targets["B"] == pytest.approx(0.2)


def test_lookahead_excludes_future_filings(conn):
    s = SingleManagerClone(label="Buffett")
    # filed_at=2024-05-15 → as_of=2024-04-01에는 보이지 않아야
    targets = s.get_target_positions(as_of_date=date(2024, 4, 1), conn=conn)
    assert targets == {}


def test_ticker_null_excluded(conn):
    # CUSIP 'XXX'가 매핑 없으면 자동 제외
    conn.execute(
        "INSERT INTO holdings (accession_no, cusip, value_usd, shares) "
        "VALUES ('a1', 'XXXNULL', 100, 1)"
    )
    s = SingleManagerClone(label="Buffett")
    targets = s.get_target_positions(as_of_date=date(2024, 6, 1), conn=conn)
    # 정규화: AAPL 800/1000, B 200/1000 → ticker=null 제외 후에도 합 1.0
    assert pytest.approx(sum(targets.values()), abs=1e-6) == 1.0
    assert "XXXNULL" not in targets

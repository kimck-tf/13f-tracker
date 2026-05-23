"""Spec §7.4: filed_at <= as_of_date 강제 가드 검증.

각 전략에 대해 미래 데이터를 절대 노출하지 않음을 확인.
"""
from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
from thirteen_f.backtest.strategies.conviction_follow import ConvictionFollow
from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK
from thirteen_f.backtest.strategies.single_manager import SingleManagerClone


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "lookahead.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.execute(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES ('cikA','Buffett','Buffett','BRK','value',1996,1.0)"
    )
    c.execute(
        """INSERT INTO filings
           VALUES ('accFUTURE','cikA','13F-HR',DATE '2024-12-31',DATE '2025-02-14',FALSE,NULL)"""
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("CUSIP_FUTURE", "FUT", False)],
    )
    c.execute(
        """INSERT INTO holdings
           VALUES ('accFUTURE','CUSIP_FUTURE','FutCo','COM',1000,10,'SH','')"""
    )
    c.execute(
        """INSERT INTO signals_quarterly
           VALUES ('cikA','CUSIP_FUTURE',DATE '2024-12-31','new',10,1000,1.0,1.0,1.0)"""
    )
    c.execute(
        """INSERT INTO total_scores
           VALUES (DATE '2024-12-31','CUSIP_FUTURE','FUT',1.0,1.0,1.0,1.0,1.0)"""
    )
    c.execute(
        """INSERT INTO consensus_quarterly
           VALUES (DATE '2024-12-31','CUSIP_FUTURE','FUT',5,5,'cikA',1.0)"""
    )
    yield c
    c.close()


def test_single_manager_blocks_future(conn):
    s = SingleManagerClone(label="Buffett")
    # filed_at=2025-02-14 미래 → as_of=2025-01-01에는 보이지 않아야
    assert s.get_target_positions(as_of_date=date(2025, 1, 1), conn=conn) == {}


def test_score_top_k_blocks_future(conn):
    s = ScoreTopK(top_k=5)
    assert s.get_target_positions(as_of_date=date(2025, 1, 1), conn=conn) == {}


def test_consensus_top_k_blocks_future(conn):
    s = ConsensusTopK(min_holders=1, top_k=5)
    assert s.get_target_positions(as_of_date=date(2025, 1, 1), conn=conn) == {}


def test_new_buy_only_blocks_future(conn):
    s = NewBuyOnly(min_holders=1, top_k=5)
    assert s.get_target_positions(as_of_date=date(2025, 1, 1), conn=conn) == {}


def test_conviction_follow_blocks_future(conn):
    s = ConvictionFollow(top_k=5)
    assert s.get_target_positions(as_of_date=date(2025, 1, 1), conn=conn) == {}


def test_after_filing_date_data_visible(conn):
    # filed_at=2025-02-14 → as_of=2025-03-01에는 보여야
    s = SingleManagerClone(label="Buffett")
    targets = s.get_target_positions(as_of_date=date(2025, 3, 1), conn=conn)
    assert "FUT" in targets

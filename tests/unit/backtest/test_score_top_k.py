from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    # total_scores: 5 종목
    rows = [
        (date(2024, 3, 31), "037833100", "AAPL", 0.5, 0.7, 0.5, 0.9, 0.65),
        (date(2024, 3, 31), "037833200", "MSFT", 0.4, 0.6, 0.4, 0.8, 0.55),
        (date(2024, 3, 31), "037833300", "GOOG", 0.3, 0.5, 0.3, 0.7, 0.45),
        (date(2024, 3, 31), "037833400", "AMZN", 0.2, 0.4, 0.2, 0.6, 0.35),
        (date(2024, 3, 31), "037833500", "META", 0.1, 0.3, 0.1, 0.5, 0.25),
    ]
    c.executemany(
        "INSERT INTO total_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    # consensus_quarterly로 holder_count
    c.executemany(
        """INSERT INTO consensus_quarterly
           (period_of_report, cusip, ticker, holder_count, new_buy_count, holder_ciks, avg_conviction)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (date(2024, 3, 31), "037833100", "AAPL", 7, 2, "c1,c2", 0.7),
            (date(2024, 3, 31), "037833200", "MSFT", 5, 1, "c1", 0.6),
            (date(2024, 3, 31), "037833300", "GOOG", 4, 0, "c1", 0.5),
            (date(2024, 3, 31), "037833400", "AMZN", 2, 0, "c1", 0.4),
            (date(2024, 3, 31), "037833500", "META", 1, 0, "c1", 0.3),
        ],
    )
    # 가짜 filings (lookahead 검증용): 모두 filed_at=2024-05-15
    c.execute(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES ('c1','Test','t','f','value',2020,1.0)"
    )
    c.execute(
        "INSERT INTO filings VALUES ('acc1','c1','13F-HR',DATE '2024-03-31',DATE '2024-05-15',FALSE,NULL)"
    )
    yield c
    c.close()


def test_score_top_k_equal_weight(conn):
    s = ScoreTopK(top_k=3)
    targets = s.get_target_positions(as_of_date=date(2024, 6, 1), conn=conn)
    assert len(targets) == 3
    # 상위 3개: AAPL, MSFT, GOOG
    assert set(targets.keys()) == {"AAPL", "MSFT", "GOOG"}
    # 동일 가중: 1/3
    for w in targets.values():
        assert w == pytest.approx(1 / 3)


def test_consensus_top_k_filters_holders(conn):
    s = ConsensusTopK(min_holders=3, top_k=10)
    targets = s.get_target_positions(as_of_date=date(2024, 6, 1), conn=conn)
    # min_holders=3 → AMZN(2), META(1) 제외
    assert set(targets.keys()) == {"AAPL", "MSFT", "GOOG"}


def test_lookahead_blocks_future_scores(conn):
    s = ScoreTopK(top_k=3)
    # filed_at=2024-05-15 → as_of=2024-04-01에는 score 보이지 않아야
    targets = s.get_target_positions(as_of_date=date(2024, 4, 1), conn=conn)
    assert targets == {}

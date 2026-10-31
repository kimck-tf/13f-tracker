from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    # total_scores: 5 종목
    rows = [
        (date(2024, 3, 31), "037833100", "AAPL", 0.5, 0.7, 0.5, 0.9, 0.65),
        (date(2024, 3, 31), "594918104", "MSFT", 0.4, 0.6, 0.4, 0.8, 0.55),
        (date(2024, 3, 31), "02079K107", "GOOG", 0.3, 0.5, 0.3, 0.7, 0.45),
        (date(2024, 3, 31), "023135106", "AMZN", 0.2, 0.4, 0.2, 0.6, 0.35),
        (date(2024, 3, 31), "30303M102", "META", 0.1, 0.3, 0.1, 0.5, 0.25),
    ]
    c.executemany(
        "INSERT INTO total_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
    )
    # consensus_quarterly로 holder_count
    c.executemany(
        """INSERT INTO consensus_quarterly
           (period_of_report, cusip, ticker, holder_count, new_buy_count,
            holder_ciks, avg_conviction)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (date(2024, 3, 31), "037833100", "AAPL", 7, 2, "c1,c2", 0.7),
            (date(2024, 3, 31), "594918104", "MSFT", 5, 1, "c1", 0.6),
            (date(2024, 3, 31), "02079K107", "GOOG", 4, 0, "c1", 0.5),
            (date(2024, 3, 31), "023135106", "AMZN", 2, 0, "c1", 0.4),
            (date(2024, 3, 31), "30303M102", "META", 1, 0, "c1", 0.3),
        ],
    )
    # ETF(SPY)와 같은 발행사의 두 클래스(530307 = LBRDA/LBRDK)
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [
            ("037833100", "AAPL", False),
            ("594918104", "MSFT", False),
            ("02079K107", "GOOG", False),
            ("023135106", "AMZN", False),
            ("30303M102", "META", False),
            ("78462F103", "SPY", True),
            ("530307107", "LBRDA", False),
            ("530307305", "LBRDK", False),
        ],
    )
    c.executemany(
        "INSERT INTO total_scores VALUES (?, ?, ?, 1.0, 1.0, 1.0, 1.0, ?)",
        [
            (date(2024, 3, 31), "78462F103", "SPY", 0.99),
            (date(2024, 3, 31), "530307107", "LBRDA", 0.41),
            (date(2024, 3, 31), "530307305", "LBRDK", 0.42),
        ],
    )
    c.executemany(
        "INSERT INTO consensus_quarterly VALUES (?, ?, ?, ?, ?, ?, 0.5)",
        [
            (date(2024, 3, 31), "78462F103", "SPY", 7, 2, "c1,c2"),
            (date(2024, 3, 31), "530307107", "LBRDA", 2, 0, "c1,c2"),
            (date(2024, 3, 31), "530307305", "LBRDK", 2, 0, "c1,c3"),
        ],
    )
    # 가짜 filings (lookahead 검증용): c1은 2024-05-15, c2는 이틀 늦은 2024-05-17 제출
    c.executemany(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES (?, ?, ?, 'f', 'value', 2020, 1.0)",
        [("c1", "Test", "t"), ("c2", "Late", "late")],
    )
    c.executemany(
        "INSERT INTO filings VALUES (?, ?, '13F-HR', DATE '2024-03-31', ?, FALSE, NULL)",
        [("acc1", "c1", date(2024, 5, 15)), ("acc2", "c2", date(2024, 5, 17))],
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


@pytest.mark.parametrize("strategy", [
    ScoreTopK(top_k=3),
    ConsensusTopK(min_holders=1, top_k=3),
    NewBuyOnly(min_holders=1, top_k=3),
])
def test_aggregate_scores_wait_until_every_manager_has_filed(conn, strategy):
    """total_scores·consensus는 그 분기 매니저 전원의 보유를 합친 값이라, 첫 제출자(05-15)가 아니라
    마지막 제출자(05-17)의 13F-HR이 공개된 뒤에야 쓸 수 있다
    (실데이터: 2025Q3 Burry 11-03 vs 나머지 11-14)."""
    assert strategy.get_target_positions(as_of_date=date(2024, 5, 16), conn=conn) == {}
    assert strategy.get_target_positions(as_of_date=date(2024, 5, 17), conn=conn) != {}


def test_new_buy_only_holds_cash_below_min_positions(conn):
    """신규매수 후보(new_buy_count >= min_holders)가 min_positions보다 적으면 소수 종목에 몰빵하지
    않고 현금을 든다 (실데이터: NVDA 100%, AER 100% 분기)."""
    # 후보: AAPL(new_buy 2), MSFT(new_buy 1) → 2종목
    assert NewBuyOnly(min_holders=1, top_k=5, min_positions=3).get_target_positions(
        as_of_date=date(2024, 6, 1), conn=conn
    ) == {}
    targets = NewBuyOnly(min_holders=1, top_k=5, min_positions=2).get_target_positions(
        as_of_date=date(2024, 6, 1), conn=conn
    )
    assert set(targets) == {"AAPL", "MSFT"}


def test_new_buy_only_name_and_params_include_min_positions():
    # 기본값(min_positions=1)은 기존 run 이름과 같아야 SPA·README의 매칭이 유지된다
    assert NewBuyOnly(min_holders=2, top_k=15).name == "NewBuyOnly(2,15)"
    s = NewBuyOnly(min_holders=2, top_k=15, min_positions=5)
    assert s.name == "NewBuyOnly(2,15,min5)"
    assert '"min_positions": 5' in s.params_json()


def test_consensus_top_k_excludes_etfs(conn):
    t = ConsensusTopK(min_holders=3, top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t  # 7명 보유·최고 점수지만 is_etf


def test_consensus_top_k_keeps_one_share_class_per_issuer(conn):
    t = ConsensusTopK(min_holders=2, top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "LBRDK" in t and "LBRDA" not in t  # 발행사 530307 → total_score 높은 클래스만
    assert "AMZN" in t  # 보유자 2명은 그대로 후보


def test_score_top_k_excludes_etfs_and_duplicate_classes(conn):
    t = ScoreTopK(top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t
    assert {"LBRDA", "LBRDK"} & set(t) == {"LBRDK"}
    assert t["LBRDK"] == pytest.approx(1 / 6)  # AAPL MSFT GOOG AMZN META LBRDK


def test_new_buy_only_merges_classes_and_excludes_etfs(conn):
    conn.execute("UPDATE consensus_quarterly SET new_buy_count = 2 WHERE ticker = 'LBRDA'")
    conn.execute("UPDATE consensus_quarterly SET new_buy_count = 1 WHERE ticker = 'LBRDK'")
    t = NewBuyOnly(min_holders=2, top_k=15).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t  # new_buy 2명이지만 ETF
    assert (
        "LBRDK" in t and "LBRDA" not in t
    )  # 발행사 신규매수 수 = max(2, 1) = 2 → 대표 클래스는 total_score 높은 LBRDK
    assert set(t) == {"AAPL", "LBRDK"}  # AAPL new_buy 2, MSFT 1은 탈락

"""Smoke tests for ConvictionFollow / NewBuyOnly / Ensemble."""
from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.conviction_follow import ConvictionFollow
from thirteen_f.backtest.strategies.ensemble import Ensemble
from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK


@pytest.fixture
def empty_conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def test_conviction_follow_empty(empty_conn):
    # 데이터 없음 → 빈 dict
    s = ConvictionFollow(top_k=10)
    assert s.get_target_positions(date(2024, 6, 1), empty_conn) == {}


def test_new_buy_only_empty(empty_conn):
    s = NewBuyOnly(min_holders=2, top_k=15)
    assert s.get_target_positions(date(2024, 6, 1), empty_conn) == {}


def test_ensemble_combines_weights():
    # Mock 두 sub-strategy
    class FixedA:
        name = "A"
        def get_target_positions(self, as_of, conn):
            return {"AAPL": 0.5, "MSFT": 0.5}
        def params_json(self):
            return "{}"
    class FixedB:
        name = "B"
        def get_target_positions(self, as_of, conn):
            return {"GOOG": 1.0}
        def params_json(self):
            return "{}"

    e = Ensemble(weights={FixedA(): 0.6, FixedB(): 0.4})
    targets = e.get_target_positions(date(2024, 6, 1), None)
    # AAPL: 0.5×0.6=0.3, MSFT: 0.5×0.6=0.3, GOOG: 1.0×0.4=0.4
    assert pytest.approx(targets["AAPL"], abs=1e-6) == 0.3
    assert pytest.approx(targets["MSFT"], abs=1e-6) == 0.3
    assert pytest.approx(targets["GOOG"], abs=1e-6) == 0.4
    assert pytest.approx(sum(targets.values()), abs=1e-6) == 1.0


def test_ensemble_rejects_unnormalized_weights():
    with pytest.raises(ValueError, match="sum"):
        Ensemble(weights={ScoreTopK(20): 0.5, ScoreTopK(10): 0.3})  # sum=0.8


def test_conviction_follow_excludes_etfs_and_merges_classes(empty_conn):
    c = empty_conn
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    c.execute(
        "INSERT INTO filings VALUES "
        "('a1', 'c1', '13F-HR', DATE '2024-03-31', DATE '2024-05-15', FALSE, NULL)"
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [
            ("78462F103", "SPY", True),
            ("530307107", "LBRDA", False),
            ("530307305", "LBRDK", False),
            ("037833100", "AAPL", False),
        ],
    )
    c.executemany(
        "INSERT INTO signals_quarterly "
        "(cik, cusip, period_of_report, change_type, weight_pct, conviction_score) "
        "VALUES ('c1', ?, DATE '2024-03-31', 'hold', 0.1, ?)",
        [("78462F103", 1.0), ("530307107", 0.9), ("530307305", 0.8), ("037833100", 0.7)],
    )
    t = ConvictionFollow(top_k=2).get_target_positions(date(2024, 6, 1), c)
    assert set(t) == {"LBRDA", "AAPL"}  # SPY 제외, 발행사당 1개, 그다음 상위 2개
    assert t["LBRDA"] == pytest.approx(0.9 / 1.6)


def test_conviction_follow_prefers_the_mapped_class_of_an_issuer(empty_conn):
    # 같은 발행사(530307)의 미매핑 형제(전환사채 등)가 conviction이 더 높아도, 순위 뒤에 걸러질
    # 그 행이 매핑된 보통주를 후보에서 밀어내면 안 된다
    c = empty_conn
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    c.execute(
        "INSERT INTO filings VALUES "
        "('a1', 'c1', '13F-HR', DATE '2024-03-31', DATE '2024-05-15', FALSE, NULL)"
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("530307107", "LBRDA", False), ("037833100", "AAPL", False)],
    )
    c.executemany(
        "INSERT INTO signals_quarterly "
        "(cik, cusip, period_of_report, change_type, weight_pct, conviction_score) "
        "VALUES ('c1', ?, DATE '2024-03-31', 'hold', 0.1, ?)",
        [("530307AB1", 0.9), ("530307107", 0.8), ("037833100", 0.7)],
    )
    t = ConvictionFollow(top_k=2).get_target_positions(date(2024, 6, 1), c)
    assert set(t) == {"LBRDA", "AAPL"}

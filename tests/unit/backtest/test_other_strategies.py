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

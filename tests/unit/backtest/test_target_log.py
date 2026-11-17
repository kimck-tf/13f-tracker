"""target_log — 그때그때 지시한 목표 종목을 쌓기만 하는 기록."""
from __future__ import annotations

import json
from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.runner import default_suite
from thirteen_f.backtest.target_log import record_targets

AS_OF = date(2024, 6, 1)


@pytest.fixture
def conn(tmp_path):
    """매니저 3명이 2024Q1 13F를 05-15에 모두 제출. ConsensusTopK(3,15) 목표 = AAA·BBB
    (CCC는 보유자 1명)."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.executemany(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES (?, ?, ?, 'f', 'value', 2020, 1.0)",
        [("c1", "Warren Buffett", "Buffett"), ("c2", "B", "Bee"), ("c3", "C", "Cee")],
    )
    c.executemany(
        "INSERT INTO filings VALUES (?, ?, '13F-HR', DATE '2024-03-31', DATE '2024-05-15', "
        "FALSE, NULL)",
        [("a1", "c1"), ("a2", "c2"), ("a3", "c3")],
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)",
        [("cusipA", "AAA"), ("cusipB", "BBB"), ("cusipC", "CCC")],
    )
    c.executemany(
        "INSERT INTO total_scores VALUES (DATE '2024-03-31', ?, ?, 1.0, 1.0, 1.0, 1.0, ?)",
        [("cusipA", "AAA", 0.9), ("cusipB", "BBB", 0.8), ("cusipC", "CCC", 0.7)],
    )
    c.executemany(
        "INSERT INTO consensus_quarterly VALUES (DATE '2024-03-31', ?, ?, ?, 0, 'c1,c2,c3', 1.0)",
        [("cusipA", "AAA", 3), ("cusipB", "BBB", 3), ("cusipC", "CCC", 1)],
    )
    yield c
    c.close()


def _log(conn, name="ConsensusTopK(3,15)"):
    rows = conn.execute(
        "SELECT as_of, period_of_report, targets_json FROM target_log "
        "WHERE strategy_name = ? ORDER BY recorded_at",
        (name,),
    ).fetchall()
    return [(as_of, period, json.loads(payload)) for as_of, period, payload in rows]


def test_first_record_stores_every_default_strategy_with_its_target(conn):
    recorded = record_targets(conn, AS_OF)
    assert recorded == [s.name for s in default_suite()]
    assert _log(conn) == [(AS_OF, date(2024, 3, 31), {"AAA": 0.5, "BBB": 0.5})]
    # 목표가 없는 전략(보유 데이터가 없는 복제)도 '현금'으로 한 줄 남긴다
    assert _log(conn, "SingleManagerClone(Druckenmiller)") == [(AS_OF, date(2024, 3, 31), {})]


def test_record_keeps_the_strategy_parameters_next_to_its_name(conn):
    """이름만으로는 전략을 가릴 수 없는 경우가 있다 — MultiManager의 이름에는 매니저 수만 들어가서
    매니저를 바꿔도 이름이 같다. 파라미터를 함께 적어 두어야 나중에 어떤 전략의 목표였는지 안다."""
    record_targets(conn, AS_OF)
    params = conn.execute(
        "SELECT params_json FROM target_log WHERE strategy_name = 'MultiManager(3 mgrs, top=20)'"
    ).fetchone()[0]
    assert json.loads(params) == {
        "mgr_labels": ["Dalio", "Druckenmiller", "Tepper"], "top_k": 20, "weighting": "equal",
    }


def test_same_name_with_other_parameters_is_recorded_as_a_change(conn, monkeypatch):
    """목표가 같아도(둘 다 보유 데이터가 없어 현금) 파라미터가 달라졌으면 새 줄을 더한다."""
    from thirteen_f.backtest import target_log
    from thirteen_f.backtest.strategies.multi_manager import MultiManager

    monkeypatch.setattr(target_log, "default_suite", lambda: [MultiManager(["Buffett"])])
    assert record_targets(conn, AS_OF) == ["MultiManager(1 mgrs, top=15)"]
    monkeypatch.setattr(target_log, "default_suite", lambda: [MultiManager(["Bee"])])
    assert record_targets(conn, date(2024, 6, 2)) == ["MultiManager(1 mgrs, top=15)"]
    labels = [
        json.loads(p)["mgr_labels"]
        for (p,) in conn.execute(
            "SELECT params_json FROM target_log ORDER BY recorded_at"
        ).fetchall()
    ]
    assert labels == [["Buffett"], ["Bee"]]


def test_record_made_before_parameters_were_stored_still_counts_as_unchanged(conn):
    """파라미터 칸이 생기기 전의 줄(NULL)은 목표만 견준다 — 같은 목표를 한 번 더 쌓지 않는다."""
    record_targets(conn, AS_OF)
    n = conn.execute("SELECT COUNT(*) FROM target_log").fetchone()[0]
    conn.execute("UPDATE target_log SET params_json = NULL")  # 옛 줄을 흉내 낸다
    assert record_targets(conn, date(2024, 6, 2)) == []
    assert conn.execute("SELECT COUNT(*) FROM target_log").fetchone()[0] == n


def test_unchanged_target_is_not_recorded_again(conn):
    record_targets(conn, AS_OF)
    assert record_targets(conn, date(2024, 6, 2)) == []
    assert len(_log(conn)) == 1


def test_changed_target_is_appended_and_the_earlier_record_stays(conn):
    """규칙이나 데이터가 바뀌어 같은 분기의 목표가 달라지면(CCC의 보유자가 3명이 됨) 새 줄을
    더한다 — analyze는 지난 분기 점수까지 다시 계산하므로, 그때 실제로 지시한 목록은 먼저 쌓아 둔
    줄에만 남는다."""
    record_targets(conn, AS_OF)
    conn.execute("UPDATE consensus_quarterly SET holder_count = 3 WHERE ticker = 'CCC'")
    assert record_targets(conn, date(2024, 6, 2)) == ["ConsensusTopK(3,15)", (
        "Ensemble(ConsensusTopK(3,10):0.5,ConsensusTopK(2,15):0.5)"
    )]
    third = pytest.approx(1 / 3, abs=1e-6)
    assert _log(conn) == [
        (AS_OF, date(2024, 3, 31), {"AAA": 0.5, "BBB": 0.5}),
        (date(2024, 6, 2), date(2024, 3, 31), {"AAA": third, "BBB": third, "CCC": third}),
    ]

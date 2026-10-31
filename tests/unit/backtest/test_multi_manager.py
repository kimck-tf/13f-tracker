"""Unit tests for MultiManager strategy — lookahead, byvalue, empty inputs."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.strategies.multi_manager import MultiManager
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "mm.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {
        "cik": "c1", "name": "Manager One", "label": "M1",
        "fund": "F1", "style": "value", "active_since": 2010,
        "cloning_score_weight": 1.0,
    })
    upsert_manager(c, {
        "cik": "c2", "name": "Manager Two", "label": "M2",
        "fund": "F2", "style": "activist", "active_since": 2012,
        "cloning_score_weight": 1.0,
    })
    upsert_filing(c, {
        "accession_no": "a1", "cik": "c1",
        "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    upsert_filing(c, {
        "accession_no": "a2", "cik": "c2",
        "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    upsert_holdings(c, "a1", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "BBB", "name_of_issuer": "Boeing", "title_of_class": "COM",
         "value_usd": 500, "shares": 5, "share_type": "SH", "put_call": ""},
    ])
    upsert_holdings(c, "a2", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 800, "shares": 4, "share_type": "SH", "put_call": ""},
        {"cusip": "CCC", "name_of_issuer": "Coke", "title_of_class": "COM",
         "value_usd": 1200, "shares": 20, "share_type": "SH", "put_call": ""},
    ])
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("AAA", "AAPL", False), ("BBB", "BA", False), ("CCC", "KO", False)],
    )
    yield c
    c.close()


def test_multi_manager_aggregates_two_managers_equal_weight(conn):
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=3)
    targets = s.get_target_positions(date(2024, 6, 1), conn)
    # AAPL(1000+800=1800), KO(1200), BA(500) — top 3
    assert set(targets.keys()) == {"AAPL", "BA", "KO"}
    assert sum(targets.values()) == pytest.approx(1.0)
    for v in targets.values():
        assert v == pytest.approx(1.0 / 3)


def test_multi_manager_byvalue_weighting(conn):
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=3, weighting="byvalue")
    targets = s.get_target_positions(date(2024, 6, 1), conn)
    # AAPL=1800, KO=1200, BA=500 → total 3500
    assert targets["AAPL"] == pytest.approx(1800 / 3500)
    assert targets["KO"] == pytest.approx(1200 / 3500)
    assert targets["BA"] == pytest.approx(500 / 3500)


def test_multi_manager_lookahead_blocks_unfiled(conn):
    # as_of < filed_at (2024-05-15) → empty
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=3)
    targets = s.get_target_positions(date(2024, 5, 1), conn)
    assert targets == {}


def test_multi_manager_top_k_limits_results(conn):
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=2)
    targets = s.get_target_positions(date(2024, 6, 1), conn)
    # top 2: AAPL + KO (BA excluded)
    assert set(targets.keys()) == {"AAPL", "KO"}


def test_multi_manager_empty_labels_returns_empty(conn):
    s = MultiManager(mgr_labels=[], top_k=3)
    assert s.get_target_positions(date(2024, 6, 1), conn) == {}


def test_multi_manager_per_manager_different_periods(tmp_path):
    """I7: 매니저별 latest period가 다를 때 각자 본인의 가장 신선한 분기 holdings 사용."""
    db = tmp_path / "diffq.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {
        "cik": "c1", "name": "M1", "label": "M1",
        "fund": "F1", "style": "value", "active_since": 2010,
        "cloning_score_weight": 1.0,
    })
    upsert_manager(c, {
        "cik": "c2", "name": "M2", "label": "M2",
        "fund": "F2", "style": "value", "active_since": 2010,
        "cloning_score_weight": 1.0,
    })
    # M1: Q1만 filing
    upsert_filing(c, {
        "accession_no": "a1q1", "cik": "c1", "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    # M2: Q2만 filing (Q1 filing 없음)
    upsert_filing(c, {
        "accession_no": "a2q2", "cik": "c2", "form_type": "13F-HR",
        "period_of_report": date(2024, 6, 30),
        "filed_at": date(2024, 8, 14),
        "is_amendment": False,
    })
    upsert_holdings(c, "a1q1", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
    ])
    upsert_holdings(c, "a2q2", [
        {"cusip": "BBB", "name_of_issuer": "Boeing", "title_of_class": "COM",
         "value_usd": 2000, "shares": 20, "share_type": "SH", "put_call": ""},
    ])
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("AAA", "AAPL", False), ("BBB", "BA", False)],
    )
    # as_of_date = Q3 시작: M1 latest = Q1, M2 latest = Q2 — 다른 분기
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=5)
    targets = s.get_target_positions(date(2024, 9, 1), c)
    # 두 매니저의 holdings가 다른 분기에서 와도 모두 집계됨
    assert set(targets.keys()) == {"AAPL", "BA"}
    assert targets["AAPL"] == pytest.approx(0.5)
    assert targets["BA"] == pytest.approx(0.5)
    c.close()


def test_multi_manager_skips_13f_nt(conn):
    """form_type LIKE '13F-HR%' 필터로 13F-NT는 제외."""
    upsert_filing(conn, {
        "accession_no": "a_nt", "cik": "c1",
        "form_type": "13F-NT",
        "period_of_report": date(2024, 6, 30),  # 더 신선
        "filed_at": date(2024, 8, 15),
        "is_amendment": False,
    })
    # a_nt에는 holdings 없음 — 그래도 latest selection이 a1로 떨어져야 정상
    s = MultiManager(mgr_labels=["M1"], top_k=5)
    targets = s.get_target_positions(date(2024, 9, 1), conn)
    # 13F-NT 무시 → a1의 AAPL+BA 잡힘
    assert set(targets.keys()) == {"AAPL", "BA"}


def test_multi_manager_excludes_etfs_and_sums_share_classes(conn):
    conn.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("78462F103", "SPY", True), ("530307107", "LBRDA", False), ("530307305", "LBRDK", False)],
    )
    # upsert_holdings는 accession의 기존 행을 지우고 다시 넣는다
    # → fixture의 AAA·BBB를 포함한 전체 목록을 준다
    upsert_holdings(
        conn,
        "a1",
        [
            {
                "cusip": "AAA",
                "name_of_issuer": "Apple",
                "title_of_class": "COM",
                "value_usd": 1000,
                "shares": 10,
                "share_type": "SH",
                "put_call": "",
            },
            {
                "cusip": "BBB",
                "name_of_issuer": "Boeing",
                "title_of_class": "COM",
                "value_usd": 500,
                "shares": 5,
                "share_type": "SH",
                "put_call": "",
            },
            {
                "cusip": "78462F103",
                "name_of_issuer": "SPDR",
                "title_of_class": "ETF",
                "value_usd": 5000,
                "shares": 10,
                "share_type": "SH",
                "put_call": "",
            },
            {
                "cusip": "530307107",
                "name_of_issuer": "Liberty",
                "title_of_class": "A",
                "value_usd": 700,
                "shares": 7,
                "share_type": "SH",
                "put_call": "",
            },
            {
                "cusip": "530307305",
                "name_of_issuer": "Liberty",
                "title_of_class": "K",
                "value_usd": 600,
                "shares": 6,
                "share_type": "SH",
                "put_call": "",
            },
        ],
    )
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=2, weighting="byvalue")
    t = s.get_target_positions(date(2024, 6, 1), conn)
    # AAPL 1800, Liberty 700+600=1300(대표 LBRDA), KO 1200 → top 2 = AAPL, LBRDA. SPY 5000은 제외
    assert set(t) == {"AAPL", "LBRDA"}
    assert t["LBRDA"] == pytest.approx(1300 / 3100)


def test_multi_manager_ignores_put_options(conn):
    """풋만 보유한 종목(Burry의 PLTR 풋)을 롱으로 사면 안 된다 — 보통주 0주."""
    upsert_holdings(conn, "a1", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "BBB", "name_of_issuer": "Boeing", "title_of_class": "COM",
         "value_usd": 5000, "shares": 50, "share_type": "SH", "put_call": "Put"},
    ])
    targets = MultiManager(mgr_labels=["M1"], top_k=5).get_target_positions(date(2024, 9, 1), conn)
    assert set(targets) == {"AAPL"}


def test_multi_manager_prefers_common_stock_over_warrants(conn):
    """같은 발행사 금액은 합치되, 대표 티커는 워런트('*W EXP …')가 아니라 보통주."""
    conn.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)",
        [("42806J114", "HTZWW"), ("42806J700", "HTZ")],
    )
    upsert_holdings(conn, "a1", [
        {"cusip": "42806J114", "name_of_issuer": "Hertz", "title_of_class": "*W EXP 06/30/205",
         "value_usd": 900, "shares": 90, "share_type": "SH", "put_call": ""},
        {"cusip": "42806J700", "name_of_issuer": "Hertz", "title_of_class": "COM NEW",
         "value_usd": 100, "shares": 10, "share_type": "SH", "put_call": ""},
    ])
    targets = MultiManager(mgr_labels=["M1"], top_k=5, weighting="byvalue").get_target_positions(
        date(2024, 9, 1), conn
    )
    assert targets == {"HTZ": pytest.approx(1.0)}

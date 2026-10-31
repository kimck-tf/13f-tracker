"""compute_signals_quarterly의 SQL 경로 — 청산(exit)·재진입(new) 행 생성."""

from datetime import date, timedelta

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.analyze.continuity import update_continuity_scores
from thirteen_f.analyze.conviction import update_conviction_scores
from thirteen_f.analyze.diff import compute_signals_quarterly
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager

Q1, Q2, Q3 = date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30)


def _mgr(c, cik):
    upsert_manager(
        c,
        {
            "cik": cik,
            "name": cik,
            "label": cik,
            "fund": "F",
            "style": "value",
            "active_since": 2020,
            "cloning_score_weight": 1.0,
        },
    )


def _filing(c, acc, cik, period):
    upsert_filing(
        c,
        {
            "accession_no": acc,
            "cik": cik,
            "form_type": "13F-HR",
            "period_of_report": period,
            "filed_at": period + timedelta(days=45),
            "is_amendment": False,
        },
    )


def _h(cusip, shares):
    return {
        "cusip": cusip,
        "name_of_issuer": cusip,
        "title_of_class": "COM",
        "value_usd": shares * 10,
        "shares": shares,
        "share_type": "SH",
        "put_call": "",
    }


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    _mgr(c, "m1")
    _mgr(c, "m2")
    for acc, cik, p in [
        ("m1q1", "m1", Q1),
        ("m1q2", "m1", Q2),
        ("m1q3", "m1", Q3),
        ("m2q1", "m2", Q1),
        ("m2q2", "m2", Q2),
    ]:
        _filing(c, acc, cik, p)
    upsert_holdings(c, "m1q1", [_h("AAA", 100), _h("BBB", 50)])
    upsert_holdings(c, "m1q2", [_h("AAA", 100)])  # BBB 전량 매도
    upsert_holdings(
        c, "m1q3", [_h("BBB", 60), _h("CCC", 10)]
    )  # AAA 전량 매도, BBB 재진입, CCC 신규
    upsert_holdings(
        c, "m2q1", [_h("AAA", 10)]
    )  # m2q2는 holdings 없음 (information table 누락 상황)
    yield c
    c.close()


def _types(conn, cik, cusip):
    return dict(
        conn.execute(
            "SELECT period_of_report, change_type FROM signals_quarterly "
            "WHERE cik = ? AND cusip = ? ORDER BY 1",
            (cik, cusip),
        ).fetchall()
    )


def test_full_liquidation_emits_exit_row(conn):
    compute_signals_quarterly(conn)
    assert _types(conn, "m1", "AAA") == {Q1: "new", Q2: "hold", Q3: "exit"}
    row = conn.execute(
        "SELECT shares_change, value_change_usd, weight_pct FROM signals_quarterly "
        "WHERE cik = 'm1' AND cusip = 'AAA' AND period_of_report = ?",
        (Q3,),
    ).fetchone()
    assert row == (-100, -1000, 0.0)


def test_reentry_after_gap_is_new_again(conn):
    compute_signals_quarterly(conn)
    assert _types(conn, "m1", "BBB") == {Q1: "new", Q2: "exit", Q3: "new"}


def test_no_rows_after_exit_and_no_exit_for_unparsed_or_missing_filings(conn):
    n = compute_signals_quarterly(conn)
    assert _types(conn, "m2", "AAA") == {
        Q1: "new"
    }  # holdings 없는 m2q2는 제출로 보지 않는다 → 거짓 exit 없음
    assert n == 3 + 3 + 1 + 1  # AAA 3 + BBB 3 + CCC 1 + m2/AAA 1


def test_exit_rows_feed_consensus_and_continuity(conn):
    compute_signals_quarterly(conn)
    update_conviction_scores(conn)
    update_continuity_scores(conn)
    compute_consensus(conn)
    assert (
        conn.execute(
            "SELECT 1 FROM consensus_quarterly WHERE cusip = 'BBB' AND period_of_report = ?", (Q2,)
        ).fetchone()
        is None
    )  # 청산한 분기엔 보유자 아님
    assert (
        conn.execute(
            "SELECT new_buy_count FROM consensus_quarterly "
            "WHERE cusip = 'BBB' AND period_of_report = ?",
            (Q3,),
        ).fetchone()[0]
        == 1
    )  # 재진입은 신규 매수
    assert conn.execute(
        "SELECT continuity_score FROM signals_quarterly WHERE cik = 'm1' AND cusip = 'BBB' "
        "AND period_of_report = ?",
        (Q3,),
    ).fetchone()[0] == pytest.approx(0.25)


def test_no_zero_share_rows_after_an_exit(conn):
    # AAA는 Q3에 청산했다. m1이 Q4에도 제출하면 AAA는 Q4에 행이 없어야 한다 (0주 hold 행 금지)
    q4 = date(2024, 12, 31)
    _filing(conn, "m1q4", "m1", q4)
    upsert_holdings(conn, "m1q4", [_h("BBB", 60), _h("CCC", 10)])
    compute_signals_quarterly(conn)
    assert _types(conn, "m1", "AAA") == {Q1: "new", Q2: "hold", Q3: "exit"}

"""`export_targets` — Plan 탭의 targets.json (기본 suite 전략별 현재 목표 비중 + 직전 대비 diff)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.backtest.runner import default_suite
from thirteen_f.web.exporter import _next_rebalance, export_targets


@pytest.fixture
def conn(tmp_path: Path):
    """매니저 3명, 2024Q1(05-15 공개)·2024Q2(08-14 공개) 두 분기.

    ConsensusTopK(3,10) 기준: Q1 = {AAA, CCC}, Q2 = {AAA, BBB} → AAA 유지, BBB 신규, CCC 매도.
    """
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.executemany(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES (?, ?, ?, 'f', 'value', 2020, 1.0)",
        [("c1", "Warren Buffett", "Buffett"), ("c2", "Bill Ackman", "Ackman"), ("c3", "C", "Cee")],
    )
    c.executemany(
        "INSERT INTO filings VALUES (?, ?, '13F-HR', ?, ?, FALSE, NULL)",
        [(f"q1{i}", f"c{i}", date(2024, 3, 31), date(2024, 5, 15)) for i in (1, 2, 3)]
        + [(f"q2{i}", f"c{i}", date(2024, 6, 30), date(2024, 8, 14)) for i in (1, 2, 3)],
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, name, sector, industry, is_etf) "
        "VALUES (?, ?, ?, ?, '', ?)",
        [("cA", "AAA", "A Corp", "Technology", False), ("cB", "BBB", "B Corp", "Energy", False),
         ("cC", "CCC", "C Corp", "Utilities", False), ("cS", "SPY", "SPDR S&P 500", "ETF", True)],
    )
    for period, scores in [
        (date(2024, 3, 31), [("cA", "AAA", 0.9, 3), ("cC", "CCC", 0.8, 3), ("cB", "BBB", 0.7, 1)]),
        (date(2024, 6, 30), [("cA", "AAA", 0.9, 3), ("cB", "BBB", 0.8, 3), ("cC", "CCC", 0.7, 1),
                             ("cS", "SPY", 0.6, 2)]),
    ]:
        for cusip, ticker, score, holders in scores:
            c.execute("INSERT INTO total_scores VALUES (?, ?, ?, 1.0, 1.0, 1.0, 1.0, ?)",
                      (period, cusip, ticker, score))
            holder_ciks = ",".join(f"c{i}" for i in range(1, holders + 1))
            c.execute("INSERT INTO consensus_quarterly VALUES (?, ?, ?, ?, 0, ?, 1.0)",
                      (period, cusip, ticker, holders, holder_ciks))
    # 복제 전략용 보유 (Buffett Q2: AAA 600 / SPY 400)
    c.executemany(
        "INSERT INTO holdings VALUES ('q21', ?, 'X', 'COM', ?, 10, 'SH', '')",
        [("cA", 600), ("cS", 400)],
    )
    c.executemany(
        "INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, ?, ?, ?)",
        [("AAA", date(2024, 8, 30), 100.0, 100.0), ("AAA", date(2024, 8, 29), 99.0, 99.0),
         ("BBB", date(2024, 8, 30), 50.0, 50.0)],
    )
    yield c
    c.close()


def _load(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "targets.json").read_text(encoding="utf-8"))


def _by_name(data: dict, name: str) -> dict:
    return next(s for s in data["strategies"] if s["name"] == name)


def test_export_targets_covers_default_suite_with_period_and_dates(conn, tmp_path: Path):
    export_targets(conn, tmp_path, as_of=date(2024, 9, 1))
    data = _load(tmp_path)
    assert data["as_of"] == "2024-09-01"
    assert [s["name"] for s in data["strategies"]] == [s.name for s in default_suite()]
    cons = _by_name(data, "ConsensusTopK(3,10)")
    assert cons["type"] == "ConsensusTopK"
    assert cons["period"] == "2024-06-30"
    assert cons["public_since"] == "2024-08-14"
    # 다음 분기말 2024-09-30 + 45일 = 2024-11-14 (목)
    assert cons["next_rebalance"] == "2024-11-14"


def test_export_targets_marks_buy_keep_and_sell_against_previous_list(conn, tmp_path: Path):
    export_targets(conn, tmp_path, as_of=date(2024, 9, 1))
    cons = _by_name(_load(tmp_path), "ConsensusTopK(3,10)")
    actions = {p["ticker"]: p["action"] for p in cons["positions"]}
    assert actions == {"AAA": "keep", "BBB": "buy"}
    assert [s["ticker"] for s in cons["sells"]] == ["CCC"]
    aaa = next(p for p in cons["positions"] if p["ticker"] == "AAA")
    assert aaa["weight"] == pytest.approx(0.5)
    assert aaa["prevWeight"] == pytest.approx(0.5)
    assert aaa["holders"] == 3 and aaa["holderIds"] == ["buffett", "ackman", "cee"]
    assert aaa["name"] == "A Corp" and aaa["sector"] == "Technology"
    assert aaa["lastClose"] == 100.0 and aaa["lastCloseDate"] == "2024-08-30"
    assert aaa["isEtf"] is False


def test_export_targets_flags_etf_positions(conn, tmp_path: Path):
    export_targets(conn, tmp_path, as_of=date(2024, 9, 1))
    clone = _by_name(_load(tmp_path), "SingleManagerClone(Buffett)")
    spy = next(p for p in clone["positions"] if p["ticker"] == "SPY")
    assert spy["isEtf"] is True
    assert spy["weight"] == pytest.approx(0.4)


def test_export_targets_recommends_best_calmar_with_enough_positions(conn, tmp_path: Path):
    """권장 = 기본 suite 최신 run 중 Calmar 1위, 단 평균 보유 8종목 이상 (몰빵 설정 제외)."""
    for run_id, name, calmar, n_pos in [
        ("r1", "ConsensusTopK(3,10)", 2.0, 10),
        ("r2", "ScoreTopK(40)", 3.0, 5),          # Calmar는 높지만 5종목 → 제외
        ("r0", "ConsensusTopK(3,10)", 9.0, 10),   # 오래된 run — 최신 run(r1)만 본다
    ]:
        conn.execute(
            "INSERT INTO backtest_runs VALUES (?, ?, '{}', DATE '2024-01-02', DATE '2024-12-31', "
            "'SPY', 10.0, ?)",
            (run_id, name, date(2024, 12, 1) if run_id != "r0" else date(2024, 1, 1)),
        )
        conn.execute(
            "INSERT INTO backtest_metrics VALUES (?, 0.3, 0.25, 1.5, 1.8, 0.12, ?, 0.7, 0.2, 0.19)",
            (run_id, calmar),
        )
        conn.executemany(
            "INSERT INTO backtest_holdings VALUES (?, DATE '2024-07-01', ?, ?)",
            [(run_id, f"T{i}", 1.0 / n_pos) for i in range(n_pos)],
        )
    export_targets(conn, tmp_path, as_of=date(2024, 9, 1))
    data = _load(tmp_path)
    assert data["recommended"] == "ConsensusTopK(3,10)"
    cons = _by_name(data, "ConsensusTopK(3,10)")
    assert cons["metrics"]["calmar"] == pytest.approx(2.0)
    assert cons["metrics"]["avgPositions"] == pytest.approx(10.0)
    assert _by_name(data, "ConvictionFollow(3)")["metrics"] is None  # run 없음


def test_export_targets_without_runs_has_no_recommendation(conn, tmp_path: Path):
    export_targets(conn, tmp_path, as_of=date(2024, 9, 1))
    assert _load(tmp_path)["recommended"] is None


def test_export_targets_before_any_filing_is_all_cash(conn, tmp_path: Path):
    export_targets(conn, tmp_path, as_of=date(2024, 5, 1))
    cons = _by_name(_load(tmp_path), "ConsensusTopK(3,10)")
    assert cons["positions"] == [] and cons["sells"] == []
    assert cons["period"] is None and cons["next_rebalance"] is None


def test_next_rebalance_rolls_weekend_deadline_to_monday():
    # 2026-09-30 + 45일 = 2026-11-14(토) → 11-16(월)
    assert _next_rebalance(date(2026, 6, 30)) == date(2026, 11, 16)
    assert _next_rebalance(date(2024, 6, 30)) == date(2024, 11, 14)

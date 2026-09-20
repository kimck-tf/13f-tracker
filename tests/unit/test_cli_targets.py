"""`thirteen-f targets` — 지금 사야 할 목표 비중을 출력하는 명령."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.cli import app


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """매니저 3명이 2024Q1 13F를 2024-05-15까지 모두 제출한 상태."""
    db_path = tmp_path / "targets.duckdb"
    init_db(db_path)
    c = duckdb.connect(str(db_path))
    c.executemany(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES (?, ?, ?, 'f', 'value', 2020, 1.0)",
        [("c1", "Warren Buffett", "Buffett"), ("c2", "B", "Bee"), ("c3", "C", "Cee")],
    )
    c.executemany(
        "INSERT INTO filings VALUES (?, ?, '13F-HR', DATE '2024-03-31', "
        "DATE '2024-05-15', FALSE, NULL)",
        [("a1", "c1"), ("a2", "c2"), ("a3", "c3")],
    )
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)",
        [("cusipA", "AAA"), ("cusipB", "BBB"), ("cusipC", "CCC")],
    )
    c.executemany(
        "INSERT INTO holdings VALUES ('a1', ?, 'X', 'COM', ?, 10, 'SH', '')",
        [("cusipA", 600), ("cusipB", 400)],
    )
    c.executemany(
        "INSERT INTO total_scores VALUES (DATE '2024-03-31', ?, ?, 1.0, 1.0, 1.0, 1.0, ?)",
        [("cusipA", "AAA", 0.9), ("cusipB", "BBB", 0.8), ("cusipC", "CCC", 0.7)],
    )
    c.executemany(
        "INSERT INTO consensus_quarterly VALUES (DATE '2024-03-31', ?, ?, ?, 0, 'c1,c2,c3', 1.0)",
        [("cusipA", "AAA", 3), ("cusipB", "BBB", 3), ("cusipC", "CCC", 1)],
    )
    c.close()
    return db_path


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, db: Path) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    monkeypatch.setenv("DUCKDB_PATH", str(db))


def test_targets_prints_ticker_and_weight_for_registry_strategy() -> None:
    """이름만 주면 default_suite와 같은 파라미터로 현재 목표 비중을 낸다."""
    result = CliRunner().invoke(app, ["targets", "--strategy", "ConsensusTopK"])
    assert result.exit_code == 0, result.output
    # min_holders=3 → CCC(보유자 1명) 제외, AAA·BBB 각 50%
    assert "AAA" in result.output and "BBB" in result.output
    assert "CCC" not in result.output
    assert "50.0%" in result.output
    assert "ConsensusTopK(3,10)" in result.output


def test_targets_accepts_parametrized_strategy_name() -> None:
    result = CliRunner().invoke(app, ["targets", "--strategy", "SingleManagerClone(Buffett)"])
    assert result.exit_code == 0, result.output
    # 보유 금액 600/400 → 60% / 40%
    assert "60.0%" in result.output and "40.0%" in result.output


def test_targets_uses_as_of_date_for_lookahead_guard() -> None:
    """--as-of로 과거 시점을 주면 그때 공개된 13F만 쓴다 (제출 전이면 빈 결과)."""
    result = CliRunner().invoke(
        app, ["targets", "--strategy", "ConsensusTopK", "--as-of", "2024-05-14"]
    )
    assert result.exit_code == 0, result.output
    assert "AAA" not in result.output
    assert "없" in result.output or "0" in result.output


def test_targets_reports_unknown_strategy_as_error() -> None:
    result = CliRunner().invoke(app, ["targets", "--strategy", "NopeStrategy"])
    assert result.exit_code != 0
    assert "Unknown strategy" in result.output


def test_targets_defaults_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    """--as-of 없이 부르면 오늘 기준 — 2024-05-15 이후이므로 목록이 나온다."""
    result = CliRunner().invoke(app, ["targets", "--strategy", "ScoreTopK"])
    assert result.exit_code == 0, result.output
    assert str(date.today()) in result.output

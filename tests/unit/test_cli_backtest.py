"""`thirteen-f backtest` — 시작일 기본값과 출력 (run_suite를 가짜로 바꿔 인자를 기록)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.backtest import runner
from thirteen_f.cli import app


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """매니저 두 명이 2024Q1 13F를 05-13, 05-15에 제출한 DB."""
    db_path = tmp_path / "13f.duckdb"
    init_db(db_path)
    c = duckdb.connect(str(db_path))
    c.executemany("INSERT INTO managers (cik, name) VALUES (?, ?)", [("c1", "A"), ("c2", "B")])
    c.executemany(
        "INSERT INTO filings VALUES (?, ?, '13F-HR', DATE '2024-03-31', ?, FALSE, NULL)",
        [("a1", "c1", date(2024, 5, 13)), ("a2", "c2", date(2024, 5, 15))],
    )
    c.close()
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    return db_path


@pytest.fixture
def suite_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[date, date]]:
    recorded: list[tuple[date, date]] = []

    def fake_run_suite(db_path, start, end, cost_bps=10.0, benchmark="SPY"):
        recorded.append((start, end))
        return [
            {
                "name": "ConsensusTopK(3,10)", "run_id": "r1",
                "start": date(2024, 5, 13), "end": date(2024, 12, 31),
                "cagr": 0.25, "mdd": 0.15, "sharpe": 1.4,
                "bench_cagr": 0.16, "bench_mdd": 0.19, "bench_sharpe": 0.98,
            }
        ]

    monkeypatch.setattr(runner, "run_suite", fake_run_suite)
    return recorded


def test_backtest_starts_at_the_first_13f_public_date_by_default(db, suite_calls):
    """시작일을 주지 않으면 첫 13F 공개일(05-13)부터다 — 그 전은 모든 전략이 현금이라 연수익률만
    낮추고, SPY는 그 기간에도 올라 같은 표 안의 비교가 어긋난다."""
    r = CliRunner().invoke(app, ["backtest", "--all", "--end", "2024-12-31"])
    assert r.exit_code == 0, r.output
    assert suite_calls == [(date(2024, 5, 13), date(2024, 12, 31))]


def test_backtest_explicit_start_wins(db, suite_calls):
    r = CliRunner().invoke(
        app, ["backtest", "--all", "--start", "2024-01-02", "--end", "2024-12-31"]
    )
    assert r.exit_code == 0, r.output
    assert suite_calls == [(date(2024, 1, 2), date(2024, 12, 31))]


def test_backtest_output_states_the_window_and_the_benchmark_row(db, suite_calls):
    """수치만 내면 구간이 다른 값끼리 섞인다 — 구간과, 같은 구간의 SPY(연수익률·낙폭·Sharpe)를
    함께 낸다."""
    r = CliRunner().invoke(app, ["backtest", "--all", "--end", "2024-12-31"])
    assert "2024-05-13 ~ 2024-12-31" in r.output
    spy = next(line for line in r.output.splitlines() if line.startswith("SPY"))
    assert "16.00%" in spy and "19.00%" in spy and "0.98" in spy

"""`thirteen-f update` — 하위 단계 호출 인자 검증 (subprocess.run을 가짜로 바꿔 기록)."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.cli import app


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "13f.duckdb"
    init_db(db_path)
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    return db_path


def _with_filing(db_path: Path, period: date) -> None:
    c = duckdb.connect(str(db_path))
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    c.execute(
        "INSERT INTO filings VALUES ('a1', 'c1', '13F-HR', ?, ?, FALSE, NULL)", (period, period)
    )
    c.close()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    recorded: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded


def _steps(calls: list[list[str]]) -> list[list[str]]:
    return [c[3:] for c in calls]  # [sys.executable, "-m", "thirteen_f.cli", *args]


def test_update_passes_db_start_quarter_to_collect(db, calls):
    _with_filing(db, date(2024, 3, 31))
    r = CliRunner().invoke(app, ["update", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls) == [["collect", "--start", "2024Q1"], ["analyze"]]


def test_update_explicit_start_wins(db, calls):
    _with_filing(db, date(2024, 3, 31))
    r = CliRunner().invoke(
        app, ["update", "--start", "2020Q1", "--skip-backtest", "--skip-export", "--skip-report"]
    )
    assert r.exit_code == 0, r.output
    assert _steps(calls)[0] == ["collect", "--start", "2020Q1"]


def test_update_with_empty_db_uses_collect_default_range(db, calls):
    r = CliRunner().invoke(app, ["update", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls)[0] == ["collect"]


def test_update_skip_collect_runs_no_collect(db, calls):
    r = CliRunner().invoke(
        app, ["update", "--skip-collect", "--skip-backtest", "--skip-export", "--skip-report"]
    )
    assert r.exit_code == 0, r.output
    assert _steps(calls) == [["analyze"]]

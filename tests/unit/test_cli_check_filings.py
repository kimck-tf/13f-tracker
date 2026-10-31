"""`thirteen-f check-filings` — 새 13F-HR이 있으면 목록과 exit 1 (자동 갱신 스크립트의 신호)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.cli import app


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "t.duckdb"
    init_db(db)
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    monkeypatch.setenv("DUCKDB_PATH", str(db))
    monkeypatch.setattr("thirteen_f.collect.edgar_client.EdgarClient", FakeClient)


def test_check_filings_exits_0_when_nothing_is_new(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", lambda *a, **k: [])
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 0, result.output
    assert "새 13F-HR 없음" in result.output


def test_check_filings_lists_new_filings_and_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    new = [{
        "label": "Buffett",
        "filer_cik": "0001067983",
        "accession_no": "0001067983-26-000001",
        "period_of_report": date(2026, 9, 30),
        "filed_at": date(2026, 11, 14),
    }]
    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", lambda *a, **k: new)
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 1, result.output
    line = next(ln for ln in result.output.splitlines() if "0001067983-26-000001" in ln)
    assert "Buffett" in line and "2026-09-30" in line and "2026-11-14" in line


def test_check_filings_exits_2_when_the_check_itself_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python의 미처리 예외도 exit 1이라, 실패를 1로 내면 자동 갱신 스크립트가 update를 돌린다."""

    def boom(*a, **k):
        raise RuntimeError("SEC 503")

    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", boom)
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 2, result.output
    assert "SEC 503" in result.output

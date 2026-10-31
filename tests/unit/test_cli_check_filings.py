"""`thirteen-f check-filings` — 새 13F-HR이 있으면 목록과 exit 1 (자동 갱신 스크립트의 신호)."""
from __future__ import annotations

from datetime import date, timedelta
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


def _filing(acc: str, period: date, filed: date, label: str = "Buffett") -> dict:
    return {
        "label": label,
        "filer_cik": "0001067983",
        "accession_no": acc,
        "period_of_report": period,
        "filed_at": filed,
    }


def test_check_filings_lists_new_filings_and_exits_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """기한이 지난 분기의 새 공시가 하나라도 있으면 exit 1 — 기한 전 공시는 대기로 함께 보인다."""
    soon = date.today() - timedelta(days=3)  # 이 분기의 기한은 아직 오지 않았다
    new = [
        _filing("0001067983-24-000017", date(2024, 3, 31), date(2024, 5, 15)),
        _filing("0001336528-xx-000001", soon, date.today(), label="Ackman"),
    ]
    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", lambda *a, **k: new)
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 1, result.output
    line = next(ln for ln in result.output.splitlines() if "0001067983-24-000017" in ln)
    assert "Buffett" in line and "2024-03-31" in line and "2024-05-15" in line
    assert "대기" in result.output and "0001336528-xx-000001" in result.output


def test_check_filings_holds_filings_whose_deadline_has_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기한 전에 collect하면 latest_public_period가 DB에 들어온 일부 제출분만으로 그 분기를 쓰므로,
    기한(분기말 + 45일, 주말·공휴일이면 다음 영업일) 다음 날 전까지는 갱신 신호를 내지 않는다."""
    period = date.today() - timedelta(days=3)
    new = [_filing("0001067983-xx-000002", period, date.today())]
    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", lambda *a, **k: new)
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 0, result.output
    assert "대기" in result.output and "0001067983-xx-000002" in result.output


def test_check_filings_exits_2_when_the_check_itself_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python의 미처리 예외도 exit 1이라, 실패를 1로 내면 자동 갱신 스크립트가 update를 돌린다."""

    def boom(*a, **k):
        raise RuntimeError("SEC 503")

    monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", boom)
    result = CliRunner().invoke(app, ["check-filings"])
    assert result.exit_code == 2, result.output
    assert "SEC 503" in result.output

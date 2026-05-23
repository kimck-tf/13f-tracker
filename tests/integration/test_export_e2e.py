"""E2E tests for `thirteen-f export`.

Two layers:
1. ``test_export_command_writes_all_json_files`` — Typer CliRunner (in-process,
   빠르고 안정적, CLI 인자 파싱·env 로딩 검증).
2. ``test_export_real_subprocess`` — ``uv run thirteen-f export`` subprocess
   (실제 entrypoint 등록·.env 로딩·sys.path 검증, I1 보강).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.cli import app
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "e2e.duckdb"
    init_db(db_path)
    c = duckdb.connect(str(db_path))
    upsert_manager(c, {
        "cik": "0000000001",
        "name": "Warren Buffett",
        "label": "Buffett",
        "fund": "Berkshire Hathaway",
        "style": "value",
        "color": "#1d6dc8",
        "active_since": 1996,
        "cloning_score_weight": 1.0,
        "notes": "test",
    })
    upsert_filing(c, {
        "accession_no": "a1",
        "cik": "0000000001",
        "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    upsert_holdings(c, "a1", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 100_000_000, "shares": 5_000_000, "share_type": "SH", "put_call": ""},
    ])
    c.execute(
        "INSERT INTO cusip_ticker_map (cusip, ticker, name, sector, industry, is_etf) "
        "VALUES ('037833100','AAPL','Apple Inc.','Technology','Consumer Electronics',FALSE)"
    )
    c.execute(
        "INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, ?, ?, ?)",
        ("AAPL", date(2024, 3, 29), 170.0, 170.0),
    )
    c.close()
    return db_path


def test_export_command_writes_all_json_files(
    tmp_path: Path,
    populated_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUCKDB_PATH", str(populated_db))
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    out = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(app, ["export", "--out", str(out)])
    assert result.exit_code == 0, f"exit={result.exit_code}\noutput={result.output}"

    expected = [
        "meta.json",
        "managers.json",
        "quarters.json",
        "quarters_index.json",
        "stocks.json",
        "holdings.json",
        "holdings_unmapped.json",
        "backtest.json",
    ]
    for fname in expected:
        path = out / fname
        assert path.exists(), f"missing {fname}; output:\n{result.output}"

    prices_dir = out / "prices"
    assert prices_dir.is_dir()
    assert (prices_dir / "AAPL.json").exists()


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv CLI not on PATH — required for subprocess invocation",
)
def test_export_real_subprocess(tmp_path: Path, populated_db: Path) -> None:
    """I1: 진짜 e2e — subprocess로 ``uv run thirteen-f export`` 호출.

    CliRunner는 in-process라 entrypoint 등록(`thirteen-f = thirteen_f.cli:app`)이나
    .env 로딩, sys.path 설정 같은 production-mode 동작이 검증되지 않음.
    이 테스트는 실제 사용자가 명령을 칠 때와 동일한 경로를 검증.
    """
    out = tmp_path / "out_subprocess"
    env = os.environ.copy()
    env["SEC_USER_AGENT"] = "test agent"
    env["DUCKDB_PATH"] = str(populated_db)
    # GOOGLE_API_KEY는 빈 값 강제 (meta.json의 llm_available=false 검증용)
    env["GOOGLE_API_KEY"] = ""

    result = subprocess.run(
        ["uv", "run", "thirteen-f", "export", "--out", str(out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"exit={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    # 핵심 파일 생성 확인
    for fname in ("meta.json", "managers.json", "quarters.json", "stocks.json", "backtest.json"):
        assert (out / fname).exists(), f"missing {fname}\noutput:\n{result.stdout}"
    # meta.json의 llm_available=false 검증
    import json as _json
    meta = _json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["llm_available"] is False

"""E2E test for `thirteen-f export` — uses Typer CliRunner (in-process).

Builds a small fixture DuckDB, invokes the command, and asserts that every
expected JSON file is produced. Avoids subprocess overhead while still exercising
the full CLI plumbing.
"""
from __future__ import annotations

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

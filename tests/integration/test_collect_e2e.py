"""E2E test for Phase 1 collection with vcrpy-recorded cassettes.

First run: requires real network + real SEC_USER_AGENT in .env.
Subsequent runs: replays recorded cassette.
"""
from datetime import date
from pathlib import Path

import duckdb
import pytest
import vcr

from scripts.init_db import init_db
from thirteen_f.collect.pipeline import run_collect
from thirteen_f.core.config import Settings


CASSETTE_DIR = Path(__file__).parent.parent / "fixtures" / "cassettes"
CASSETTE_DIR.mkdir(parents=True, exist_ok=True)

# 기본: 'none' (재생만, 네트워크 X). 새 cassette 녹화 시 RECORD_VCR=1 명시.
import os as _os
_record_mode = "once" if _os.environ.get("RECORD_VCR") == "1" else "none"

my_vcr = vcr.VCR(
    cassette_library_dir=str(CASSETTE_DIR),
    record_mode=_record_mode,
    match_on=["method", "scheme", "host", "port", "path"],
    filter_headers=[("user-agent", "REDACTED")],
)


@pytest.mark.integration
def test_collect_buffett_one_quarter(tmp_path):
    db = tmp_path / "test.duckdb"
    init_db(db)
    managers_yaml = tmp_path / "managers.yaml"
    managers_yaml.write_text(
        '- name: "Warren Buffett"\n'
        '  label: "Buffett"\n'
        '  cik: "0001067983"\n'
        '  fund: "Berkshire Hathaway"\n'
        '  style: "value"\n'
        '  active_since: 1996\n'
        '  cloning_score_weight: 1.0\n',
        encoding="utf-8",
    )

    settings = Settings(
        sec_user_agent="Test User test@example.com",
        openfigi_api_key="",
        duckdb_path=db,
    )

    with my_vcr.use_cassette("buffett_2024q1.yaml"):
        stats = run_collect(
            settings=settings,
            managers_yaml=managers_yaml,
            db_path=db,
            start_date=date(2024, 1, 1),
        )

    assert stats["managers"] == 1
    assert stats["filings_parsed"] >= 1
    assert stats["holdings_rows"] >= 10  # Buffett 보유 종목 수

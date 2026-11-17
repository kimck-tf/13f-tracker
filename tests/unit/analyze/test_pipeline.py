"""run_analyze — scoring.toml 설정이 분석 단계에 전달되는지."""
from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.pipeline import run_analyze
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager

WEIGHTS = "[weights]\nconsensus=0.30\nconviction=0.30\ncontinuity=0.20\ncloning_quality=0.20\n"


def _holding(cusip, value):
    return {
        "cusip": cusip,
        "name_of_issuer": cusip,
        "title_of_class": "COM",
        "value_usd": value,
        "shares": value,
        "share_type": "SH",
        "put_call": "",
    }


@pytest.fixture
def db(tmp_path):
    """매니저 M의 13F: 자기 회사 OWN 900 + 종목 AAA 100."""
    path = tmp_path / "t.duckdb"
    init_db(path)
    c = duckdb.connect(str(path))
    upsert_manager(
        c,
        {
            "cik": "c1",
            "name": "Manager",
            "label": "M",
            "fund": "F",
            "style": "value",
            "active_since": 2020,
            "cloning_score_weight": 1.0,
        },
    )
    upsert_filing(
        c,
        {
            "accession_no": "a1",
            "cik": "c1",
            "form_type": "13F-HR",
            "period_of_report": date(2024, 3, 31),
            "filed_at": date(2024, 5, 15),
            "is_amendment": False,
        },
    )
    upsert_holdings(c, "a1", [_holding("OWN", 900), _holding("AAA", 100)])
    c.close()
    return path


def _weights(db):
    c = duckdb.connect(str(db), read_only=True)
    try:
        return dict(c.execute("SELECT cusip, weight_pct FROM signals_quarterly").fetchall())
    finally:
        c.close()


def test_run_analyze_leaves_out_affiliated_holdings_listed_in_scoring_toml(db, tmp_path):
    toml = tmp_path / "scoring.toml"
    toml.write_text(WEIGHTS + '\n[affiliated_holdings]\nM = ["OWN"]\n', encoding="utf-8")
    run_analyze(db, toml)
    assert _weights(db) == {"AAA": pytest.approx(1.0)}


def test_run_analyze_without_affiliated_section_keeps_every_holding(db, tmp_path):
    toml = tmp_path / "scoring.toml"
    toml.write_text(WEIGHTS, encoding="utf-8")
    run_analyze(db, toml)
    assert _weights(db) == {"OWN": pytest.approx(0.9), "AAA": pytest.approx(0.1)}

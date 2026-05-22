"""Unit tests for web/exporter.py — verify JSON dumps match Pydantic schemas."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import upsert_filing, upsert_manager
from thirteen_f.web.exporter import (
    _avatar_from_name,
    export_managers,
    export_meta,
    export_quarters,
)
from thirteen_f.web.schemas import Manager, Meta, QuarterEntry


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {
        "cik": "0000000001",
        "name": "Warren Buffett",
        "label": "Buffett",
        "fund": "Berkshire Hathaway",
        "style": "value",
        "color": "#1d6dc8",
        "active_since": 1996,
        "cloning_score_weight": 1.0,
        "notes": "13F 추종 원조",
    })
    upsert_manager(c, {
        "cik": "0000000002",
        "name": "Bill Ackman",
        "label": "Ackman",
        "fund": "Pershing Square",
        "style": "activist",
        "color": "#0e8a3b",
        "active_since": 2004,
        "cloning_score_weight": 1.0,
        "notes": "초집중",
    })
    for acc, cik, pr, fa in [
        ("a1", "0000000001", date(2024, 3, 31), date(2024, 5, 15)),
        ("a2", "0000000001", date(2024, 6, 30), date(2024, 8, 14)),
        ("a3", "0000000002", date(2024, 6, 30), date(2024, 8, 14)),
    ]:
        upsert_filing(c, {
            "accession_no": acc,
            "cik": cik,
            "form_type": "13F-HR",
            "period_of_report": pr,
            "filed_at": fa,
            "is_amendment": False,
        })
    yield c
    c.close()


def test_avatar_from_name():
    assert _avatar_from_name("Warren Buffett") == "WB"
    assert _avatar_from_name("Li Lu") == "LL"
    assert _avatar_from_name("Single") == "S"


def test_export_managers_writes_valid_schema(conn, tmp_path: Path):
    export_managers(conn, tmp_path)
    data = json.loads((tmp_path / "managers.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    for m in data:
        Manager.model_validate(m)  # schema 검증
        assert len(m["avatar"]) <= 2
        assert m["color"].startswith("#")
    # id == label lowercased
    ids = {m["id"] for m in data}
    assert ids == {"buffett", "ackman"}


def test_export_quarters_orders_and_indexes(conn, tmp_path: Path):
    export_quarters(conn, tmp_path)
    quarters = json.loads((tmp_path / "quarters.json").read_text(encoding="utf-8"))
    idx_map = json.loads((tmp_path / "quarters_index.json").read_text(encoding="utf-8"))
    # 2 distinct periods
    assert [q["date"] for q in quarters] == ["2024-03-31", "2024-06-30"]
    assert quarters[0]["key"] == "2024Q1"
    assert quarters[0]["label"] == "Q1'24"
    assert quarters[1]["key"] == "2024Q2"
    assert quarters[1]["label"] == "Q2'24"
    assert idx_map == {"2024-03-31": 0, "2024-06-30": 1}
    for q in quarters:
        QuarterEntry.model_validate(q)


def test_export_meta_includes_counts_and_llm_flag(conn, tmp_path: Path):
    export_meta(conn, tmp_path, llm_available=False)
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    Meta.model_validate(meta)
    assert meta["mgr_count"] == 2
    assert meta["latest_period"] == "2024-06-30"
    assert meta["llm_available"] is False
    assert meta["data_version"]  # non-empty

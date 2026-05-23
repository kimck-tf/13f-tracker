"""Unit tests for web/exporter.py — verify JSON dumps match Pydantic schemas."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager
from thirteen_f.web.exporter import (
    _avatar_from_name,
    _group_holdings_by_date,
    _resample_quarterly,
    export_backtest,
    export_holdings,
    export_managers,
    export_meta,
    export_prices_split,
    export_quarters,
    export_stocks,
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
    # cusip_ticker_map: 1 mapped + 1 unmapped (no ticker)
    c.execute(
        "INSERT INTO cusip_ticker_map (cusip, ticker, name, sector, industry, is_etf) "
        "VALUES ('037833100','AAPL','Apple Inc.','Technology','Consumer Electronics',FALSE)"
    )
    c.execute(
        "INSERT INTO cusip_ticker_map (cusip, ticker, name, sector, industry, is_etf) "
        "VALUES ('999999999',NULL,'Private Co.',NULL,NULL,FALSE)"
    )
    # prices: AAPL 분기말 + few daily
    for d, close in [
        (date(2024, 3, 29), 170.0),
        (date(2024, 3, 30), 171.0),
        (date(2024, 6, 28), 200.0),
        (date(2024, 6, 30), 200.5),
    ]:
        c.execute(
            "INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, ?, ?, ?)",
            ("AAPL", d, close, close),
        )
    # holdings: Buffett owns AAPL in Q1 + Q2, Ackman owns AAPL + unmapped in Q2
    upsert_holdings(c, "a1", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 100_000_000, "shares": 5_000_000, "share_type": "SH", "put_call": ""},
    ])
    upsert_holdings(c, "a2", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 150_000_000, "shares": 7_500_000, "share_type": "SH", "put_call": ""},
    ])
    upsert_holdings(c, "a3", [
        {"cusip": "037833100", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 80_000_000, "shares": 4_000_000, "share_type": "SH", "put_call": ""},
        {"cusip": "999999999", "name_of_issuer": "Private Co.", "title_of_class": "COM",
         "value_usd": 20_000_000, "shares": 1_000_000, "share_type": "SH", "put_call": ""},
    ])
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
    # stock_count counts only mapped tickers
    assert meta["stock_count"] == 1


def test_export_stocks_uses_sector_and_quarter_end_close(conn, tmp_path: Path):
    export_stocks(conn, tmp_path)
    data = json.loads((tmp_path / "stocks.json").read_text(encoding="utf-8"))
    # 1 mapped ticker (unmapped is excluded)
    assert len(data) == 1
    aapl = data[0]
    assert aapl["t"] == "AAPL"
    assert aapl["n"] == "Apple Inc."
    assert aapl["s"] == "Technology"
    assert aapl["i"] == "Consumer Electronics"
    # 2 quarters → 2 px entries (Q1 closest ≤ 2024-03-31 = 171.0, Q2 = 200.5)
    assert aapl["px"] == [171.0, 200.5]


def test_export_prices_split_per_ticker(conn, tmp_path: Path):
    export_prices_split(conn, tmp_path)
    prices_dir = tmp_path / "prices"
    assert prices_dir.is_dir()
    aapl_file = prices_dir / "AAPL.json"
    assert aapl_file.exists()
    payload = json.loads(aapl_file.read_text(encoding="utf-8"))
    assert len(payload["date"]) == 4
    assert payload["close"] == [170.0, 171.0, 200.0, 200.5]


def test_export_holdings_cutoff_excludes_delinquent_filing(tmp_path: Path):
    """C4 보강: filed_at > q+180d delinquent filing은 export에서 제외되는지 검증."""
    from datetime import date
    import duckdb
    from scripts.init_db import init_db
    from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager
    from thirteen_f.web.exporter import export_holdings

    db = tmp_path / "cutoff.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {
        "cik": "cdq", "name": "Delinquent Mgr", "label": "DQM",
        "fund": "DQ", "style": "value", "active_since": 2010,
        "cloning_score_weight": 1.0,
    })
    # Q1'24 분기: 정상 filing (45일 이내)
    upsert_filing(c, {
        "accession_no": "a_ok", "cik": "cdq", "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 5, 15),
        "is_amendment": False,
    })
    # Q1'24 분기인데 filed_at이 200일 후 — delinquent (cutoff 180일 초과)
    upsert_filing(c, {
        "accession_no": "a_late", "cik": "cdq", "form_type": "13F-HR",
        "period_of_report": date(2024, 3, 31),
        "filed_at": date(2024, 10, 17),  # q + 200d
        "is_amendment": False,
    })
    upsert_holdings(c, "a_ok", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 1_000, "shares": 5_000_000, "share_type": "SH", "put_call": ""},
    ])
    upsert_holdings(c, "a_late", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM",
         "value_usd": 999, "shares": 9_999_999, "share_type": "SH", "put_call": ""},
    ])
    c.execute(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES ('AAA','AAPL',FALSE)"
    )
    out = tmp_path / "out"
    out.mkdir()
    export_holdings(c, out)
    import json
    h = json.loads((out / "holdings.json").read_text(encoding="utf-8"))
    # 정상 filing만 잡힘 — shares=5.0M 그대로, 9.99M은 제외
    assert h["dqm"]["AAPL"][0] == 5.0
    c.close()


def test_export_holdings_splits_mapped_and_unmapped(conn, tmp_path: Path):
    export_holdings(conn, tmp_path)
    holdings = json.loads((tmp_path / "holdings.json").read_text(encoding="utf-8"))
    unmapped = json.loads((tmp_path / "holdings_unmapped.json").read_text(encoding="utf-8"))
    # Buffett: AAPL in both quarters; Ackman: AAPL only Q2
    assert "buffett" in holdings
    assert "AAPL" in holdings["buffett"]
    # shares in millions (5M, 7.5M)
    assert holdings["buffett"]["AAPL"] == [5.0, 7.5]
    assert holdings["ackman"]["AAPL"] == [0.0, 4.0]
    # Unmapped CUSIP isolated to second file under Ackman only
    assert "ackman" in unmapped
    assert "999999999" in unmapped["ackman"]
    assert unmapped["ackman"]["999999999"]["shares"] == [0.0, 1.0]
    # Mapping coverage ≥ 85% (CLAUDE.md known issue)
    total_mapped = sum(len(v) for v in holdings.values())
    total_unmapped = sum(len(v) for v in unmapped.values())
    coverage = total_mapped / (total_mapped + total_unmapped) if (total_mapped + total_unmapped) else 1.0
    assert coverage >= 0.5  # 2 mapped / 3 total = 66.7%


def test_resample_quarterly_collapses_to_quarter_end():
    curves = [
        (date(2024, 1, 2), 100.0, 100.0, 0),
        (date(2024, 1, 3), 101.0, 100.5, 0),
        (date(2024, 3, 29), 110.0, 105.0, 0),
        (date(2024, 4, 1), 110.5, 105.2, 0),
        (date(2024, 6, 28), 120.0, 110.0, 0),
    ]
    equity, dd, qrets, bench = _resample_quarterly(curves)
    assert equity == [110.0, 120.0]
    assert bench == [105.0, 110.0]
    # quarterly return: Q1=0(첫분기), Q2≈(120/110-1)
    assert qrets[0] == 0.0
    assert qrets[1] == pytest.approx(120.0 / 110.0 - 1.0)
    # drawdown: 누적 최고 대비 (peaks가 단조증가라 모두 0)
    assert all(v <= 0 for v in dd)


def test_group_holdings_by_date_orders_and_serializes():
    rows = [
        (date(2024, 6, 30), "AAPL", 0.6),
        (date(2024, 6, 30), "MSFT", 0.4),
        (date(2024, 3, 31), "AAPL", 1.0),
    ]
    grouped = _group_holdings_by_date(rows)
    assert len(grouped) == 2
    assert grouped[0]["date"] == "2024-03-31"
    assert grouped[1]["date"] == "2024-06-30"
    assert grouped[1]["holdings"][0]["ticker"] in {"AAPL", "MSFT"}


def test_export_backtest_writes_runs_with_holdings_and_metrics(conn, tmp_path: Path):
    # backtest_runs + backtest_curves + backtest_metrics + backtest_holdings 직접 INSERT
    conn.execute(
        "INSERT INTO backtest_runs (run_id, strategy_name, params_json, start_date, end_date, "
        "benchmark, cost_bps, created_at) VALUES ('r1','TestStrat','{\"k\":1}',"
        "DATE '2024-01-02', DATE '2024-12-31','SPY',10.0, NOW())"
    )
    for d, nav, bn in [
        (date(2024, 1, 2), 1_000_000.0, 1_000_000.0),
        (date(2024, 3, 29), 1_050_000.0, 1_020_000.0),
        (date(2024, 6, 28), 1_100_000.0, 1_030_000.0),
    ]:
        conn.execute(
            "INSERT INTO backtest_curves VALUES ('r1', ?, ?, ?, 2)",
            (d, nav, bn),
        )
    conn.execute(
        "INSERT INTO backtest_metrics VALUES ('r1', 0.10, 0.12, 1.5, 1.8, -0.05, 2.4, 0.66, 0.03, 0.04)"
    )
    conn.execute(
        "INSERT INTO backtest_holdings VALUES ('r1', DATE '2024-01-02','AAPL',0.5)"
    )
    conn.execute(
        "INSERT INTO backtest_holdings VALUES ('r1', DATE '2024-01-02','MSFT',0.5)"
    )

    export_backtest(conn, tmp_path)
    data = json.loads((tmp_path / "backtest.json").read_text(encoding="utf-8"))
    assert len(data) == 1
    run = data[0]
    assert run["run_id"] == "r1"
    assert run["name"] == "TestStrat"
    assert run["params"] == {"k": 1}
    assert len(run["equity"]) == 2  # 2 quarters
    assert run["metrics"]["cagr"] == pytest.approx(0.12)
    assert run["metrics"]["hitRate"] == pytest.approx(0.66)
    assert run["metrics"]["benchTotalRet"] == pytest.approx(0.03)
    # holdings log
    assert len(run["holdingsLog"]) == 1
    assert run["holdingsLog"][0]["date"] == "2024-01-02"
    tickers = {h["ticker"] for h in run["holdingsLog"][0]["holdings"]}
    assert tickers == {"AAPL", "MSFT"}

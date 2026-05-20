from unittest.mock import MagicMock, patch

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.cusip_mapper import (
    fetch_cache,
    upsert_mapping,
    fill_missing,
)


@pytest.fixture
def db_path(tmp_path):
    p = tmp_path / "test.duckdb"
    init_db(p)
    return p


def test_fetch_cache_empty(db_path):
    conn = duckdb.connect(str(db_path))
    assert fetch_cache(conn, ["037833100"]) == {}
    conn.close()


def test_upsert_and_fetch(db_path):
    conn = duckdb.connect(str(db_path))
    upsert_mapping(conn, [
        {"cusip": "037833100", "ticker": "AAPL", "figi": "BBG0", "name": "Apple", "is_etf": False},
    ])
    result = fetch_cache(conn, ["037833100", "000000000"])
    assert result["037833100"]["ticker"] == "AAPL"
    assert "000000000" not in result
    conn.close()


def test_fill_missing_uses_cache_first(db_path):
    conn = duckdb.connect(str(db_path))
    upsert_mapping(conn, [{"cusip": "037833100", "ticker": "AAPL", "figi": "", "name": "Apple", "is_etf": False}])
    # OpenFIGI mock — 호출되지 않아야 함
    with patch("thirteen_f.collect.cusip_mapper._openfigi_batch") as mock_api:
        fill_missing(conn, ["037833100"], api_key=None)
        mock_api.assert_not_called()
    conn.close()


def test_fill_missing_calls_openfigi_for_misses(db_path):
    conn = duckdb.connect(str(db_path))
    with patch("thirteen_f.collect.cusip_mapper._openfigi_batch") as mock_api:
        mock_api.return_value = [
            {"cusip": "037833100", "ticker": "AAPL", "figi": "BBG0", "name": "Apple Inc", "is_etf": False}
        ]
        fill_missing(conn, ["037833100"], api_key=None)
    # 캐시에 적재 확인
    row = conn.execute(
        "SELECT ticker FROM cusip_ticker_map WHERE cusip='037833100'"
    ).fetchone()
    assert row[0] == "AAPL"
    conn.close()

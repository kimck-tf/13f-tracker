from unittest.mock import MagicMock, patch

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.cusip_mapper import (
    fetch_cache,
    upsert_mapping,
    fill_missing,
    _pick_us_primary,
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


def test_pick_us_primary_returns_us_when_mixed():
    """외국 거래소가 먼저 와도 US primary를 우선 선택."""
    data = [
        {"exchCode": "GZ", "ticker": "016", "name": "VEREN INC"},
        {"exchCode": "UN", "ticker": "AAPL", "name": "APPLE INC"},
    ]
    assert _pick_us_primary(data)["ticker"] == "AAPL"


def test_pick_us_primary_none_when_no_us():
    """외국 거래소만 있으면 None — ticker=None으로 두어 yfinance 호출 회피."""
    data = [
        {"exchCode": "GZ", "ticker": "016"},
        {"exchCode": "XH", "ticker": "CPG2CAD"},
        {"exchCode": "XF", "ticker": "CPG2CAD"},
    ]
    assert _pick_us_primary(data) is None


def test_pick_us_primary_handles_nasdaq_codes():
    """NASDAQ 변형 코드(UQ/UR/UP/UW) 모두 US로 인정."""
    for code in ("UQ", "UR", "UP", "UW", "UA", "UF", "UV", "UD", "US"):
        data = [{"exchCode": code, "ticker": "TEST"}]
        assert _pick_us_primary(data) is not None, f"exchCode={code} should match"


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

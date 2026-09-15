from datetime import date

import duckdb
import pandas as pd
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.price_loader import _upsert_prices, to_stooq_ticker


def test_to_stooq_ticker_simple():
    assert to_stooq_ticker("AAPL") == "AAPL.US"


def test_to_stooq_ticker_class_share():
    # Spec §5.6: 클래스주 '.' → '-' + '.US'
    assert to_stooq_ticker("BRK.B") == "BRK-B.US"
    assert to_stooq_ticker("BF.B") == "BF-B.US"


def test_upsert_prices_skips_rows_with_nan_close(tmp_path):
    """yfinance가 확정 전 거래일을 NaN 가격으로 주는 경우(2026-09 확인) — NaN이 저장되면
    백테스트 NAV 전체가 NaN이 되므로 그 행은 저장하지 않는다."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    conn = duckdb.connect(str(db))
    nan = float("nan")
    df = pd.DataFrame(
        {"Open": [1.0, nan], "High": [1.0, nan], "Low": [1.0, nan],
         "Close": [1.0, nan], "Adj Close": [1.0, nan], "Volume": [10, 0]},
        index=pd.to_datetime(["2026-09-11", "2026-09-14"]),
    )

    assert _upsert_prices(conn, "AAA", df) == 1
    assert conn.execute(
        "SELECT date, adj_close FROM prices WHERE ticker = 'AAA'"
    ).fetchall() == [(date(2026, 9, 11), 1.0)]
    conn.close()

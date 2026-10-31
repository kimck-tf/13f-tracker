from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from scripts.init_db import init_db
from thirteen_f.collect import price_loader
from thirteen_f.collect.price_loader import _upsert_prices, download_prices, to_stooq_ticker


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


def _frame(start: date, n: int, close=100.0, adj_scale=1.0):
    idx = pd.to_datetime([start + timedelta(days=i) for i in range(n)])
    closes = [close] * n
    adjs = [close * adj_scale] * n
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Adj Close": adjs,
            "Volume": [1] * n,
        },
        index=idx,
    )


def _seed(conn, ticker, start, n, close=100.0):
    conn.executemany(
        "INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        [(ticker, start + timedelta(days=i), close, close, close, close, close) for i in range(n)],
    )


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def _fake(monkeypatch, frames):
    """frames: 호출 순서대로 돌려줄 DataFrame 리스트. 호출 인자 (ticker, start)를 기록한다."""
    calls = []

    def fake(ticker, start):
        calls.append((ticker, start))
        return frames.pop(0)

    monkeypatch.setattr(price_loader, "_yfinance_download", fake)
    return calls


def test_download_prices_fetches_from_overlap_window_when_history_exists(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)  # 09-01 ~ 09-14 저장됨
    calls = _fake(monkeypatch, [_frame(date(2026, 9, 4), 17)])  # 09-04 ~ 09-20, 값 동일
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert calls == [("AAA", date(2026, 9, 4))]  # 마지막 날 − 10일부터
    assert conn.execute(
        "SELECT COUNT(*), MAX(date) FROM prices WHERE ticker = 'AAA'"
    ).fetchone() == (20, date(2026, 9, 20))


def test_download_prices_rescales_history_after_dividend_or_split(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    new = _frame(date(2026, 9, 4), 17, adj_scale=0.9)  # 배당 조정: 겹치는 날의 Adj Close가 0.9배
    new.iloc[-1, new.columns.get_loc("Adj Close")] = float("nan")  # 마지막 날은 미확정 NaN
    calls = _fake(monkeypatch, [new])
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert len(calls) == 1  # 전체 재다운로드 없이
    hist = conn.execute(
        "SELECT DISTINCT adj_close FROM prices WHERE ticker = 'AAA' AND date < DATE '2026-09-04'"
    ).fetchall()
    assert hist == [(pytest.approx(90.0),)]  # 이전 이력이 같은 비율로 재스케일
    assert conn.execute("SELECT DISTINCT close FROM prices WHERE ticker = 'AAA'").fetchall() == [
        (100.0,)
    ]


def test_download_prices_refetches_everything_when_overlap_disagrees(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    bad = _frame(date(2026, 9, 4), 17, adj_scale=0.9)
    bad.iloc[0, bad.columns.get_loc("Adj Close")] = (
        50.0  # 비율이 날마다 다름 → 조정이 아니라 데이터 수정
    )
    full = _frame(date(2024, 1, 1), 5, close=7.0)
    calls = _fake(monkeypatch, [bad, full])
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert calls[1] == ("AAA", date(2024, 1, 1))
    assert (
        conn.execute("SELECT COUNT(*) FROM prices WHERE ticker = 'AAA' AND close = 7.0").fetchone()[
            0
        ]
        == 5
    )


def test_download_prices_uses_start_for_unknown_ticker(conn, monkeypatch):
    calls = _fake(monkeypatch, [_frame(date(2024, 1, 2), 3)])
    download_prices(conn, ["NEW"], start=date(2024, 1, 1))
    assert calls == [("NEW", date(2024, 1, 1))]

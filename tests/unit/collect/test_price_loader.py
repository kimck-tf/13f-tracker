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
    # 배치 경로는 비워 둔다 — 실제 yfinance가 네트워크로 받아 와 단일 경로 fake를 건너뛰지 않게
    monkeypatch.setattr(price_loader, "_yf_batch", lambda tickers, start: {}, raising=False)
    return calls


def test_download_prices_fetches_from_overlap_window_when_history_exists(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)  # 09-01 ~ 09-14 저장됨
    calls = _fake(monkeypatch, [_frame(date(2026, 9, 4), 17)])  # 09-04 ~ 09-20, 값 동일
    download_prices(conn, ["AAA"], start=date(2026, 9, 1))
    assert calls == [("AAA", date(2026, 9, 4))]  # 마지막 날 − 10일부터
    assert conn.execute(
        "SELECT COUNT(*), MAX(date) FROM prices WHERE ticker = 'AAA'"
    ).fetchone() == (20, date(2026, 9, 20))


def test_download_prices_rescales_history_after_dividend_or_split(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    new = _frame(date(2026, 9, 4), 17, adj_scale=0.9)  # 배당 조정: 겹치는 날의 Adj Close가 0.9배
    # 저장 범위 안의 마지막 겹침일(09-14)이 미확정 NaN — 비율은 두 쪽 모두 값이 있는 09-13로 구하고,
    # upsert가 건너뛰는 09-14도 같은 비율로 재스케일돼야 한다
    new.iloc[10, new.columns.get_loc("Adj Close")] = float("nan")
    calls = _fake(monkeypatch, [new])
    download_prices(conn, ["AAA"], start=date(2026, 9, 1))
    assert len(calls) == 1  # 전체 재다운로드 없이
    hist = conn.execute("SELECT DISTINCT adj_close FROM prices WHERE ticker = 'AAA'").fetchall()
    assert hist == [(pytest.approx(90.0),)]  # 저장 이력 전체가 같은 비율로 재스케일
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
    download_prices(conn, ["AAA"], start=date(2026, 9, 1))
    assert calls[1] == ("AAA", date(2026, 9, 1))
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


def test_download_prices_batches_tickers_with_the_same_start(conn, monkeypatch):
    batch_calls = []

    def fake_batch(tickers, start):
        batch_calls.append((tuple(tickers), start))
        return {t: _frame(date(2024, 1, 2), 3) for t in tickers if t != "MISSING"}

    single_calls = []

    def fake_single(ticker, start):
        single_calls.append((ticker, start))
        return _frame(date(2024, 1, 2), 3)

    monkeypatch.setattr(price_loader, "_yf_batch", fake_batch)
    monkeypatch.setattr(price_loader, "_yfinance_download", fake_single)
    download_prices(conn, ["AAA", "BBB", "MISSING"], start=date(2024, 1, 1))
    assert batch_calls == [(("AAA", "BBB", "MISSING"), date(2024, 1, 1))]
    assert single_calls == [("MISSING", date(2024, 1, 1))]  # 배치에 빠진 종목만 단일 경로
    assert conn.execute("SELECT COUNT(DISTINCT ticker) FROM prices").fetchone()[0] == 3


def test_download_prices_refetches_when_stored_history_breaks_inside_the_overlap(
    conn, monkeypatch
):
    # 저장 이력 안의 단절(09-07까지 200, 09-08부터 100) + 새 값은 모두 100.
    # 마지막 날 비율만 보면 1이라 겹치는 구간만 덮어쓰고 단절이 09-04로 옮겨 남는다
    # → 전체를 다시 받아야 한다
    _seed(conn, "AAA", date(2026, 9, 1), 7, close=200.0)
    _seed(conn, "AAA", date(2026, 9, 8), 7, close=100.0)
    calls = _fake(monkeypatch, [_frame(date(2026, 9, 4), 17), _frame(date(2026, 9, 1), 20)])
    download_prices(conn, ["AAA"], start=date(2026, 9, 1))
    assert calls == [("AAA", date(2026, 9, 4)), ("AAA", date(2026, 9, 1))]
    closes = conn.execute("SELECT DISTINCT close FROM prices WHERE ticker = 'AAA'").fetchall()
    assert closes == [(100.0,)]


def test_download_prices_ignores_zero_prices_in_the_overlap(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    new = _frame(date(2026, 9, 4), 17, adj_scale=0.9)
    for col in ("Close", "Adj Close"):
        new.iloc[10, new.columns.get_loc(col)] = 0.0  # 09-14에 잘못 들어온 0 가격
    _fake(monkeypatch, [new])
    download_prices(conn, ["AAA"], start=date(2026, 9, 1))  # ZeroDivisionError 없이 끝난다
    hist = conn.execute(
        "SELECT DISTINCT adj_close FROM prices WHERE ticker = 'AAA' AND date < DATE '2026-09-14'"
    ).fetchall()
    assert hist == [(pytest.approx(90.0),)]


def test_download_prices_backfills_when_start_precedes_stored_history(conn, monkeypatch):
    # 수집 범위를 앞당기면(update --start 2020Q1) 이미 있는 ticker도 start부터 받아야
    # 앞부분이 비지 않는다
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    calls = _fake(monkeypatch, [_frame(date(2024, 1, 2), 3)])
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert calls == [("AAA", date(2024, 1, 1))]


def test_download_prices_refetches_when_only_one_stored_day_overlaps(conn, monkeypatch):
    """겹치는 날이 하루뿐이면(거래가 드문 종목) 비율 하나로는 배당·분할과 데이터 정정을 구별할 수
    없다 — 0.3% 다르다고 저장 이력 전체에 곱하지 말고 처음부터 다시 받는다."""
    _seed(conn, "AAA", date(2026, 7, 17), 1)
    _seed(conn, "AAA", date(2026, 9, 14), 1)  # 겹침 창(09-04 ~ 09-14)에는 이 하루만 있다
    full = _frame(date(2024, 1, 1), 5, close=7.0)
    calls = _fake(monkeypatch, [_frame(date(2026, 9, 4), 17, close=100.3), full])
    download_prices(conn, ["AAA"], start=date(2026, 7, 17))
    assert calls[1] == ("AAA", date(2026, 7, 17))
    assert conn.execute(
        "SELECT close FROM prices WHERE ticker = 'AAA' AND date = DATE '2026-07-17'"
    ).fetchone() == (100.0,)  # 재스케일되지 않았다

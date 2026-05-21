"""Daily price downloader: yfinance → Stooq fallback. Spec §5.1-1f, §5.6."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


def to_stooq_ticker(yf_ticker: str) -> str:
    """Spec §5.6: BRK.B → BRK-B.US."""
    return yf_ticker.replace(".", "-") + ".US"


def _yf_try(ticker: str, start: date) -> pd.DataFrame | None:
    """yfinance 단일 시도 — 빈 결과 시 None."""
    try:
        import yfinance as yf

        df = yf.download(
            ticker,
            start=start.isoformat(),
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        logger.warning("yfinance failed for %s: %s", ticker, e)
        return None


def _yfinance_download(ticker: str, start: date) -> pd.DataFrame | None:
    """yfinance + 1회 휴리스틱 재시도. yfinance는 timeout/일시적 404 시 빈
    DataFrame을 반환하므로 약 2초 대기 후 한 번 더 시도하여 GOOGL·RH 같은
    intermittent 실패를 복구."""
    import time
    df = _yf_try(ticker, start)
    if df is not None and not df.empty:
        return df
    time.sleep(2.0)
    return _yf_try(ticker, start)


def _stooq_download(ticker: str, start: date) -> pd.DataFrame | None:
    """Stooq CSV 직접 fetch. STOOQ_API_KEY 환경변수 필요 (2024년 이후 무인증 폐지).
    키 없으면 즉시 None 반환 — 시끄러운 로그·시간낭비 회피.

    키 발급: https://stooq.com/q/d/?s=AAPL.US&get_apikey 에서 captcha 입력 후 발급.
    """
    import os
    api_key = os.environ.get("STOOQ_API_KEY", "").strip().strip('"')
    if not api_key:
        return None
    try:
        import httpx
        from io import StringIO

        stooq_t = to_stooq_ticker(ticker)
        url = (
            f"https://stooq.com/q/d/l/?s={stooq_t}"
            f"&d1={start.strftime('%Y%m%d')}&i=d&apikey={api_key}"
        )
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or text.lower().startswith("no data") or "\n" not in text:
            return None
        df = pd.read_csv(StringIO(text))
        if df.empty or "Date" not in df.columns:
            return None
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df["Adj Close"] = df["Close"]
        return df
    except Exception as e:
        logger.warning("Stooq failed for %s: %s", ticker, e)
        return None


def _upsert_prices(
    conn: duckdb.DuckDBPyConnection, ticker: str, df: pd.DataFrame
) -> int:
    rows: list[tuple] = []
    for idx, row in df.iterrows():
        try:
            d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
            rows.append(
                (
                    ticker,
                    d,
                    float(row.get("Open", float("nan"))),
                    float(row.get("High", float("nan"))),
                    float(row.get("Low", float("nan"))),
                    float(row.get("Close", float("nan"))),
                    float(row.get("Adj Close", row.get("Close", float("nan")))),
                    int(row.get("Volume", 0) or 0),
                )
            )
        except Exception as e:
            logger.warning("Row skipped for %s on %s: %s", ticker, idx, e)
    if not rows:
        return 0
    conn.executemany(
        """
        INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (ticker, date) DO UPDATE SET
            open=excluded.open, high=excluded.high, low=excluded.low,
            close=excluded.close, adj_close=excluded.adj_close, volume=excluded.volume
        """,
        rows,
    )
    return len(rows)


def download_prices(
    conn: duckdb.DuckDBPyConnection,
    tickers: Iterable[str],
    start: date,
    failure_log: Path | None = None,
) -> dict[str, int]:
    """Download daily prices for tickers; return {ticker: row_count}.
    Tickers with no data after both yfinance and Stooq are appended to failure_log.
    """
    results: dict[str, int] = {}
    failed: list[str] = []
    for t in sorted(set(t for t in tickers if t)):
        df = _yfinance_download(t, start)
        if df is None or df.empty:
            df = _stooq_download(t, start)
        if df is None or df.empty:
            logger.error("Both sources failed for %s", t)
            failed.append(t)
            results[t] = 0
            continue
        results[t] = _upsert_prices(conn, t, df)
    if failed and failure_log is not None:
        failure_log.parent.mkdir(parents=True, exist_ok=True)
        with failure_log.open("a", encoding="utf-8") as f:
            for t in failed:
                f.write(json.dumps({"ticker": t, "ts": date.today().isoformat()}) + "\n")
    return results

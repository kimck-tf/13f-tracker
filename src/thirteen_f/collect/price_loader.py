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


def _yfinance_download(ticker: str, start: date) -> pd.DataFrame | None:
    """Try yfinance. Returns DataFrame or None on failure."""
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
        # yfinance multi-level columns 평탄화
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception as e:
        logger.warning("yfinance failed for %s: %s", ticker, e)
        return None


def _stooq_download(ticker: str, start: date) -> pd.DataFrame | None:
    try:
        from pandas_datareader import data as pdr

        stooq_t = to_stooq_ticker(ticker)
        df = pdr.DataReader(stooq_t, "stooq", start=start)
        if df is None or df.empty:
            return None
        # stooq returns descending; flip
        df = df.sort_index()
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

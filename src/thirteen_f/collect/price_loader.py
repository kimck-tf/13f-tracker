"""Daily price downloader: yfinance → Stooq fallback. Spec §5.1-1f, §5.6."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

OVERLAP_DAYS = 10  # 증분 다운로드 때 마지막 저장일보다 이만큼 앞에서부터 받아 겹치는 구간을 만든다
ADJ_TOLERANCE = 1e-4  # 겹치는 날의 값이 이 비율 안에서 같으면 같은 값으로 본다
BATCH_SIZE = 50  # yfinance 한 번에 받는 ticker 수


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
        from io import StringIO

        import httpx

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
        # 확정 전 거래일은 가격이 NaN으로 온다 — 저장하면 백테스트 NAV 전체가 NaN이 되므로 건너뛰고
        # 다음 수집 때 채운다 (engine은 빠진 날을 직전 가격으로 채움)
        if pd.isna(row.get("Close")) or pd.isna(row.get("Adj Close", row.get("Close"))):
            continue
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


def _last_price_dates(conn: duckdb.DuckDBPyConnection) -> dict[str, date]:
    """ticker별 저장된 마지막 가격 날짜."""
    return dict(conn.execute("SELECT ticker, MAX(date) FROM prices GROUP BY ticker").fetchall())


def _yf_batch(tickers: list[str], start: date) -> dict[str, pd.DataFrame]:
    """yfinance 한 번의 요청으로 여러 ticker를 받아 ticker별 단일 레벨 컬럼 DataFrame으로 나눈다.

    값이 전부 NaN인 ticker(조회 실패·상장 전)는 빼고, 요청 자체가 실패하면 빈 dict를 돌려준다 —
    빠진 ticker는 호출자가 단일 경로(`_fetch`)로 다시 받는다.
    """
    try:
        import yfinance as yf

        df = yf.download(
            tickers,
            start=start.isoformat(),
            group_by="ticker",
            auto_adjust=False,
            threads=True,
            progress=False,
        )
    except Exception as e:
        logger.warning("yfinance batch failed for %d tickers: %s", len(tickers), e)
        return {}
    if df is None or df.empty or not isinstance(df.columns, pd.MultiIndex):
        return {}
    out: dict[str, pd.DataFrame] = {}
    present = set(df.columns.get_level_values(0))
    for t in tickers:
        if t not in present:
            continue
        sub = df[t].dropna(how="all")
        if not sub.empty:
            out[t] = sub
    return out


def _fetch(ticker: str, start: date) -> pd.DataFrame | None:
    """yfinance, 비어 있으면 Stooq. 둘 다 비면 None."""
    df = _yfinance_download(ticker, start)
    if df is None or df.empty:
        df = _stooq_download(ticker, start)
    if df is None or df.empty:
        return None
    return df


def _overlap_pairs(
    conn: duckdb.DuckDBPyConnection, ticker: str, df: pd.DataFrame
) -> list[tuple[float, float, float, float]]:
    """새로 받은 df와 DB에 모두 있는 날의 (새 close, 새 adj_close, DB close, DB adj_close), 날짜순.

    새 값이 NaN인 날(확정 전 거래일)과 DB 값이 0 이하인 날은 뺀다.
    """
    first = df.index.min().date()
    stored = {
        d: (c, a)
        for d, c, a in conn.execute(
            "SELECT date, close, adj_close FROM prices WHERE ticker = ? AND date >= ?",
            (ticker, first),
        ).fetchall()
    }
    pairs: list[tuple[float, float, float, float]] = []
    for idx, row in df.sort_index().iterrows():
        d = idx.date()
        new_close, new_adj = row.get("Close"), row.get("Adj Close", row.get("Close"))
        if d not in stored or pd.isna(new_close) or pd.isna(new_adj):
            continue
        db_close, db_adj = stored[d]
        if not db_close or not db_adj or db_close <= 0 or db_adj <= 0:
            continue
        pairs.append((float(new_close), float(new_adj), float(db_close), float(db_adj)))
    return pairs


def download_prices(
    conn: duckdb.DuckDBPyConnection,
    tickers: Iterable[str],
    start: date,
    failure_log: Path | None = None,
) -> dict[str, int]:
    """Download daily prices for tickers; return {ticker: row_count}.

    이미 가격이 있는 ticker는 마지막 저장일 `OVERLAP_DAYS`일 전부터만 받는다. 겹치는 날의
    수정 종가가 상수 배율로 달라졌으면(배당·분할의 소급 조정) 그 전 이력을 같은 배율로
    재스케일하고, 배율이 날마다 다르면(데이터 정정) `start`부터 전체를 다시 받는다.
    yfinance 요청은 fetch 시작일이 같은 ticker끼리 `BATCH_SIZE`개씩 묶어 보내고, 배치 결과에 없는
    ticker만 단일 경로(yfinance → Stooq)로 다시 받는다.
    Tickers with no data after both yfinance and Stooq are appended to failure_log.
    """
    results: dict[str, int] = {}
    failed: list[str] = []
    last_dates = _last_price_dates(conn)
    todo = sorted(set(t for t in tickers if t))
    fetch_start = {
        t: start if last_dates.get(t) is None else last_dates[t] - timedelta(days=OVERLAP_DAYS)
        for t in todo
    }
    by_start: dict[date, list[str]] = {}
    for t in todo:
        by_start.setdefault(fetch_start[t], []).append(t)
    batched: dict[str, pd.DataFrame] = {}
    for s, group in by_start.items():
        for i in range(0, len(group), BATCH_SIZE):
            batched.update(_yf_batch(group[i:i + BATCH_SIZE], s))
    for t in todo:
        last = last_dates.get(t)
        df = batched.get(t)
        if df is None:
            df = _fetch(t, fetch_start[t])
        if df is not None and last is not None:
            pairs = _overlap_pairs(conn, t, df)
            if pairs:
                new_close, new_adj, db_close, db_adj = pairs[-1]
                r_adj, r_close = new_adj / db_adj, new_close / db_close
                if abs(r_adj - 1) > ADJ_TOLERANCE or abs(r_close - 1) > ADJ_TOLERANCE:
                    consistent = all(
                        abs(na / (da * r_adj) - 1) <= ADJ_TOLERANCE
                        and abs(nc / (dc * r_close) - 1) <= ADJ_TOLERANCE
                        for nc, na, dc, da in pairs
                    )
                    if consistent:
                        first = df.index.min().date()
                        conn.execute(
                            "UPDATE prices SET adj_close = adj_close * ?, open = open * ?, "
                            "high = high * ?, low = low * ?, close = close * ? "
                            "WHERE ticker = ? AND date < ?",
                            (r_adj, r_close, r_close, r_close, r_close, t, first),
                        )
                        logger.info(
                            "Rescaled %s history before %s (adj x%.6f, close x%.6f)",
                            t, first, r_adj, r_close,
                        )
                    else:
                        logger.info("Overlap for %s disagrees; refetching from %s", t, start)
                        df = _fetch(t, start)
        if df is None:
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

"""One-shot backfill: populate cusip_ticker_map.sector/industry/name via yfinance.

Idempotent — only updates rows where sector is NULL or empty. Re-run after
adding new tickers. Safe to interrupt; partial progress persists.
"""
from __future__ import annotations

import logging
import sys

import duckdb

logger = logging.getLogger(__name__)


def main() -> int:
    import yfinance as yf  # heavy import → lazy

    from thirteen_f.core.config import load_settings

    settings = load_settings()
    conn = duckdb.connect(str(settings.duckdb_path))
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT ticker
            FROM cusip_ticker_map
            WHERE ticker IS NOT NULL
              AND (sector IS NULL OR sector = '')
            ORDER BY ticker
            """
        ).fetchall()
    except duckdb.BinderException as e:
        print(f"Schema missing sector/industry columns — run init_db first. ({e})", file=sys.stderr)
        return 2

    if not rows:
        print("Nothing to backfill — all rows already have sector.")
        return 0

    print(f"Backfilling sector/industry for {len(rows)} tickers...")
    ok = 0
    err = 0
    for (ticker,) in rows:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as e:  # noqa: BLE001 — network errors are non-fatal
            print(f"  ERR {ticker}: {e}", file=sys.stderr)
            err += 1
            continue
        sector = info.get("sector") or "Other"
        industry = info.get("industry") or ""
        long_name = info.get("longName") or info.get("shortName") or ""
        conn.execute(
            """
            UPDATE cusip_ticker_map
            SET sector = ?,
                industry = ?,
                name = COALESCE(NULLIF(name, ''), ?)
            WHERE ticker = ?
            """,
            (sector, industry, long_name, ticker),
        )
        print(f"  OK  {ticker}: {sector} / {industry}")
        ok += 1

    print(f"Done — {ok} updated, {err} errors.")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

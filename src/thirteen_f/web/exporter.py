"""DuckDB → JSON dumper for static SPA (Phase 5).

Each export_* function writes one or more JSON files to ``out_dir``. The JSON
schema is defined in :mod:`thirteen_f.web.schemas` (SSOT).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from .schemas import Manager, Meta, QuarterEntry


def _avatar_from_name(name: str) -> str:
    """'Warren Buffett' -> 'WB'."""
    return "".join(w[0] for w in name.split() if w)[:2].upper()


def export_managers(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``managers.json`` — list of Manager records.

    id = label (lowercased), avatar derived from full name initials.
    """
    rows = conn.execute(
        """
        SELECT label, name, fund, style, color, notes
        FROM managers
        ORDER BY label
        """
    ).fetchall()
    payload = []
    for label, name, fund, style, color, notes in rows:
        if not label:
            continue
        payload.append(
            Manager(
                id=label.lower(),
                name=name,
                firm=fund or "",
                style=style or "",
                color=color or "#1d6dc8",
                avatar=_avatar_from_name(name),
                note=notes or "",
            ).model_dump()
        )
    (out_dir / "managers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_quarters(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``quarters.json`` (ordered list) and ``quarters_index.json`` (date→idx)."""
    rows = conn.execute(
        """
        SELECT DISTINCT period_of_report
        FROM filings
        WHERE period_of_report IS NOT NULL
        ORDER BY period_of_report
        """
    ).fetchall()
    payload: list[dict] = []
    idx_map: dict[str, int] = {}
    for i, (period,) in enumerate(rows):
        q = (period.month - 1) // 3 + 1
        year_short = f"{period.year % 100:02d}"
        key = f"{period.year}Q{q}"
        label = f"Q{q}'{year_short}"
        iso = period.isoformat()
        payload.append(
            QuarterEntry(key=key, label=label, date=iso).model_dump()
        )
        idx_map[iso] = i
    (out_dir / "quarters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "quarters_index.json").write_text(
        json.dumps(idx_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_meta(
    conn: duckdb.DuckDBPyConnection,
    out_dir: Path,
    llm_available: bool,
) -> None:
    """Export ``meta.json`` — single Meta record summarising the dump."""
    mgr_count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
    stock_count = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM cusip_ticker_map WHERE ticker IS NOT NULL"
    ).fetchone()[0]
    latest = conn.execute(
        "SELECT MAX(period_of_report) FROM filings"
    ).fetchone()[0]
    now = datetime.now(UTC)
    meta = Meta(
        generated_at=now,
        latest_period=latest.isoformat() if latest else "",
        data_version=str(int(now.timestamp())),
        mgr_count=mgr_count,
        stock_count=stock_count,
        llm_available=llm_available,
    )
    (out_dir / "meta.json").write_text(
        meta.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _quarter_end_dates(conn: duckdb.DuckDBPyConnection) -> list:
    rows = conn.execute(
        """
        SELECT DISTINCT period_of_report FROM filings
        WHERE period_of_report IS NOT NULL ORDER BY period_of_report
        """
    ).fetchall()
    return [r[0] for r in rows]


def export_stocks(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``stocks.json`` — per-ticker name/sector/industry + quarter-end close series.

    Source: ``cusip_ticker_map`` (sector/industry must be backfilled via
    ``scripts/supplement_sector.py``); falls back to "Other" if missing.
    """
    q_dates = _quarter_end_dates(conn)
    rows = conn.execute(
        """
        SELECT ticker,
               COALESCE(NULLIF(name, ''), ticker)    AS display_name,
               COALESCE(NULLIF(sector, ''), 'Other') AS sector,
               COALESCE(industry, '')                AS industry
        FROM cusip_ticker_map
        WHERE ticker IS NOT NULL
        ORDER BY ticker
        """
    ).fetchall()
    payload: list[dict] = []
    for ticker, display_name, sector, industry in rows:
        px: list[float | None] = []
        for qd in q_dates:
            row = conn.execute(
                """
                SELECT close FROM prices
                WHERE ticker = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
                """,
                (ticker, qd),
            ).fetchone()
            px.append(float(row[0]) if row and row[0] is not None else None)
        payload.append({
            "t": ticker,
            "n": display_name,
            "s": sector,
            "i": industry or None,
            "px": px,
        })
    (out_dir / "stocks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_prices_split(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``prices/{TICKER}.json`` — one file per ticker, daily close series.

    Lazy-loaded by the SPA only when a stock detail page is opened.
    """
    prices_dir = out_dir / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    tickers = conn.execute(
        "SELECT DISTINCT ticker FROM prices WHERE ticker IS NOT NULL ORDER BY ticker"
    ).fetchall()
    for (ticker,) in tickers:
        rows = conn.execute(
            "SELECT date, close FROM prices WHERE ticker = ? ORDER BY date",
            (ticker,),
        ).fetchall()
        payload = {
            "date": [r[0].isoformat() for r in rows],
            "close": [float(r[1]) if r[1] is not None else None for r in rows],
        }
        (prices_dir / f"{ticker}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


def export_holdings(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``holdings.json`` and ``holdings_unmapped.json``.

    Shape: ``{manager_label: {ticker: [shares_per_quarter_in_millions]}}``.
    Unmapped CUSIPs (no ticker in cusip_ticker_map) are isolated into the
    second file so the SPA can ignore them safely while preserving raw data.
    """
    quarters = _quarter_end_dates(conn)
    q_count = len(quarters)
    managers = conn.execute("SELECT cik, label FROM managers ORDER BY label").fetchall()
    payload: dict[str, dict[str, list[float]]] = {}
    unmapped: dict[str, dict[str, dict]] = {}

    for cik, label in managers:
        if not label:
            continue
        mgr_id = label.lower()
        by_ticker: dict[str, list[float]] = {}
        unmapped_rows: dict[str, dict] = {}
        for i, q in enumerate(quarters):
            cutoff = q + timedelta(days=180)
            rows = conn.execute(
                """
                SELECT h.cusip, m.ticker, h.name_of_issuer, SUM(h.shares) AS shares
                FROM holdings h
                JOIN filings f ON f.accession_no = h.accession_no
                LEFT JOIN cusip_ticker_map m ON m.cusip = h.cusip
                WHERE f.cik = ? AND f.period_of_report = ?
                  AND f.filed_at <= ? AND f.superseded_by IS NULL
                GROUP BY h.cusip, m.ticker, h.name_of_issuer
                """,
                (cik, q, cutoff),
            ).fetchall()
            for cusip, ticker, name, shares in rows:
                shares_m = float(shares or 0) / 1e6  # 백만주 단위
                if ticker:
                    by_ticker.setdefault(ticker, [0.0] * q_count)[i] = shares_m
                else:
                    entry = unmapped_rows.setdefault(
                        cusip,
                        {"name_of_issuer": name or "", "shares": [0.0] * q_count},
                    )
                    entry["shares"][i] = shares_m
        payload[mgr_id] = by_ticker
        if unmapped_rows:
            unmapped[mgr_id] = unmapped_rows

    (out_dir / "holdings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "holdings_unmapped.json").write_text(
        json.dumps(unmapped, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

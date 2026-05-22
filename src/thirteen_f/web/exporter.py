"""DuckDB → JSON dumper for static SPA (Phase 5).

Each export_* function writes one or more JSON files to ``out_dir``. The JSON
schema is defined in :mod:`thirteen_f.web.schemas` (SSOT).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
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

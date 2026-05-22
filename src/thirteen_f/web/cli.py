"""CLI helpers for web/ — DuckDB → JSON dump orchestrator."""
from __future__ import annotations

from pathlib import Path

import duckdb
import typer

from . import exporter


def do_export(out: Path, llm_available: bool, db_path: str) -> None:
    """Run all exporter.export_* in deterministic order.

    Connects to ``db_path`` read-only. ``out`` and ``out/prices`` are created
    if missing. ``llm_available`` is forwarded to ``meta.json``.
    """
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        out.mkdir(parents=True, exist_ok=True)
        (out / "prices").mkdir(parents=True, exist_ok=True)

        typer.echo("Exporting managers / quarters ...")
        exporter.export_managers(conn, out)
        exporter.export_quarters(conn, out)

        typer.echo("Exporting stocks / prices / holdings ...")
        exporter.export_stocks(conn, out)
        exporter.export_prices_split(conn, out)
        exporter.export_holdings(conn, out)

        typer.echo("Exporting backtest ...")
        exporter.export_backtest(conn, out)

        exporter.export_meta(conn, out, llm_available=llm_available)
        typer.echo(f"OK Exported to {out}")
    finally:
        conn.close()

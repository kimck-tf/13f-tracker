"""DuckDB → pandas DataFrame helpers.

Migrated from src/thirteen_f/dashboard/tables.py in Phase 5 (Plan A1).
The dashboard/tables.py module now re-exports from here for backward compatibility.
"""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd


def latest_period(conn: duckdb.DuckDBPyConnection) -> date | None:
    row = conn.execute("SELECT MAX(period_of_report) FROM filings").fetchone()
    return row[0] if row else None


def manager_list(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute(
        "SELECT cik, label, name, fund, style, active_since, cloning_score_weight FROM managers ORDER BY label"
    ).fetchdf()


def top_scores(conn: duckdb.DuckDBPyConnection, period: date, top_n: int = 50) -> pd.DataFrame:
    return conn.execute(
        """
        SELECT ticker, cusip, total_score, consensus_score, conviction_score,
               continuity_score, cloning_quality_score
        FROM total_scores
        WHERE period_of_report = ?
        ORDER BY total_score DESC NULLS LAST
        LIMIT ?
        """,
        (period, top_n),
    ).fetchdf()


def manager_history(conn: duckdb.DuckDBPyConnection, cik: str) -> pd.DataFrame:
    return conn.execute(
        """
        SELECT s.period_of_report, s.cusip, m.ticker, s.change_type, s.weight_pct,
               s.conviction_score, s.continuity_score
        FROM signals_quarterly s
        LEFT JOIN cusip_ticker_map m ON s.cusip = m.cusip
        WHERE s.cik = ?
        ORDER BY s.period_of_report DESC, s.weight_pct DESC
        """,
        (cik,),
    ).fetchdf()


def backtest_curves_df(conn: duckdb.DuckDBPyConnection, run_ids: list[str]) -> pd.DataFrame:
    if not run_ids:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in run_ids)
    return conn.execute(
        f"""
        SELECT c.run_id, r.strategy_name, c.date, c.nav, c.benchmark_nav, c.position_count
        FROM backtest_curves c
        JOIN backtest_runs r ON c.run_id = r.run_id
        WHERE c.run_id IN ({placeholders})
        ORDER BY c.run_id, c.date
        """,
        run_ids,
    ).fetchdf()


def backtest_metrics_df(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return conn.execute(
        """
        SELECT r.run_id, r.strategy_name, r.start_date, r.end_date, r.cost_bps,
               m.total_return, m.cagr, m.sharpe, m.sortino, m.mdd, m.calmar,
               m.win_rate_quarterly, m.bench_total_return, m.bench_cagr
        FROM backtest_runs r
        JOIN backtest_metrics m ON r.run_id = m.run_id
        ORDER BY r.created_at DESC
        """
    ).fetchdf()


def get_read_only_conn(db_path: str):
    return duckdb.connect(db_path, read_only=True)

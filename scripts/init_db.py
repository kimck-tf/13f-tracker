"""Initialize DuckDB schema for 13F tracker (Spec §4.2)."""
from __future__ import annotations

from pathlib import Path

import duckdb

EXPECTED_TABLES = {
    "managers",
    "filings",
    "holdings",
    "cusip_ticker_map",
    "prices",
    "signals_quarterly",
    "consensus_quarterly",
    "total_scores",
    "backtest_runs",
    "backtest_curves",
    "backtest_metrics",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS managers (
    cik VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    label VARCHAR,
    fund VARCHAR,
    style VARCHAR,
    active_since INTEGER,
    cloning_score_weight DOUBLE DEFAULT 1.0,
    color VARCHAR DEFAULT '',
    notes VARCHAR DEFAULT ''
);

CREATE TABLE IF NOT EXISTS filings (
    accession_no VARCHAR PRIMARY KEY,
    cik VARCHAR NOT NULL REFERENCES managers(cik),
    form_type VARCHAR NOT NULL,
    period_of_report DATE NOT NULL,
    filed_at DATE NOT NULL,
    is_amendment BOOLEAN DEFAULT FALSE,
    superseded_by VARCHAR
);

CREATE TABLE IF NOT EXISTS holdings (
    accession_no   VARCHAR NOT NULL REFERENCES filings(accession_no),
    cusip          VARCHAR NOT NULL,
    name_of_issuer VARCHAR,
    title_of_class VARCHAR NOT NULL DEFAULT '',
    value_usd      BIGINT,
    shares         BIGINT,
    share_type     VARCHAR,
    put_call       VARCHAR NOT NULL DEFAULT '',
    PRIMARY KEY (accession_no, cusip, title_of_class, put_call)
);

CREATE TABLE IF NOT EXISTS cusip_ticker_map (
    cusip      VARCHAR PRIMARY KEY,
    ticker     VARCHAR,
    figi       VARCHAR,
    name       VARCHAR,
    is_etf     BOOLEAN,
    updated_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prices (
    ticker    VARCHAR,
    date      DATE,
    open      DOUBLE,
    high      DOUBLE,
    low       DOUBLE,
    close     DOUBLE,
    adj_close DOUBLE,
    volume    BIGINT,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS signals_quarterly (
    cik VARCHAR, cusip VARCHAR, period_of_report DATE,
    change_type VARCHAR,
    shares_change BIGINT, value_change_usd BIGINT,
    weight_pct DOUBLE,
    conviction_score DOUBLE,
    continuity_score DOUBLE,
    PRIMARY KEY (cik, cusip, period_of_report)
);

CREATE TABLE IF NOT EXISTS consensus_quarterly (
    period_of_report DATE, cusip VARCHAR,
    ticker VARCHAR,
    holder_count INTEGER,
    new_buy_count INTEGER,
    holder_ciks VARCHAR,
    avg_conviction DOUBLE,
    PRIMARY KEY (period_of_report, cusip)
);

CREATE TABLE IF NOT EXISTS total_scores (
    period_of_report DATE, cusip VARCHAR,
    ticker VARCHAR,
    consensus_score DOUBLE,
    conviction_score DOUBLE,
    continuity_score DOUBLE,
    cloning_quality_score DOUBLE,
    total_score DOUBLE,
    PRIMARY KEY (period_of_report, cusip)
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id VARCHAR PRIMARY KEY,
    strategy_name VARCHAR NOT NULL,
    params_json VARCHAR,
    start_date DATE, end_date DATE,
    benchmark VARCHAR DEFAULT 'SPY',
    cost_bps DOUBLE,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backtest_curves (
    run_id VARCHAR REFERENCES backtest_runs(run_id),
    date DATE, nav DOUBLE, benchmark_nav DOUBLE,
    position_count INTEGER,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    run_id VARCHAR PRIMARY KEY REFERENCES backtest_runs(run_id),
    total_return DOUBLE, cagr DOUBLE,
    sharpe DOUBLE, sortino DOUBLE,
    mdd DOUBLE, calmar DOUBLE,
    win_rate_quarterly DOUBLE,
    bench_total_return DOUBLE, bench_cagr DOUBLE
);
"""


# Idempotent in-place migrations for DBs created before Phase 5 (Plan A2/A3).
MIGRATIONS = [
    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS color VARCHAR DEFAULT ''",
    "ALTER TABLE managers ADD COLUMN IF NOT EXISTS notes VARCHAR DEFAULT ''",
]


def init_db(db_path: Path | str) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA_SQL)
        for sql in MIGRATIONS:
            conn.execute(sql)
    finally:
        conn.close()


if __name__ == "__main__":
    from thirteen_f.core.config import load_settings
    settings = load_settings()
    init_db(settings.duckdb_path)
    print(f"Initialized DuckDB at {settings.duckdb_path}")

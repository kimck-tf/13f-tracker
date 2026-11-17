
import duckdb

from scripts.init_db import EXPECTED_TABLES, init_db


def test_init_db_creates_all_tables(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()
    assert tables == EXPECTED_TABLES


def test_init_db_idempotent(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    init_db(db_path)  # 두 번 호출해도 에러 X
    conn = duckdb.connect(str(db_path), read_only=True)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    conn.close()
    assert tables == EXPECTED_TABLES


def test_init_db_adds_benchmark_risk_columns_to_an_existing_db(tmp_path):
    """2026-11 전에 만든 DB에는 backtest_metrics.bench_mdd·bench_sharpe가 없다 — init_db가 더하고
    이미 있던 run의 지표는 그대로 둔다 (새 칸은 NULL)."""
    db_path = tmp_path / "old.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "CREATE TABLE backtest_metrics (run_id VARCHAR PRIMARY KEY, total_return DOUBLE, "
        "cagr DOUBLE, sharpe DOUBLE, sortino DOUBLE, mdd DOUBLE, calmar DOUBLE, "
        "win_rate_quarterly DOUBLE, bench_total_return DOUBLE, bench_cagr DOUBLE)"
    )
    conn.execute(
        "INSERT INTO backtest_metrics VALUES ('r1', 0.5, 0.2, 1.3, 1.5, 0.15, 1.4, 0.7, 0.4, 0.18)"
    )
    conn.close()
    init_db(db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    row = conn.execute(
        "SELECT cagr, bench_cagr, bench_mdd, bench_sharpe FROM backtest_metrics WHERE run_id = 'r1'"
    ).fetchone()
    conn.close()
    assert row == (0.2, 0.18, None, None)


def test_holdings_pk_no_null(tmp_path):
    db_path = tmp_path / "test.duckdb"
    init_db(db_path)
    conn = duckdb.connect(str(db_path))
    conn.execute(
        "INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight) "
        "VALUES ('0000000001','Test','t','Fund','value',2020,1.0)"
    )
    conn.execute(
        "INSERT INTO filings VALUES "
        "('acc1','0000000001','13F-HR',DATE '2024-03-31',DATE '2024-05-15',FALSE,NULL)"
    )
    # put_call DEFAULT '' 검증: NULL 대신 '' 저장
    conn.execute(
        "INSERT INTO holdings (accession_no, cusip, value_usd, shares) "
        "VALUES ('acc1','123456789',1000,10)"
    )
    row = conn.execute(
        "SELECT put_call, title_of_class FROM holdings WHERE cusip='123456789'"
    ).fetchone()
    assert row == ("", "")
    conn.close()

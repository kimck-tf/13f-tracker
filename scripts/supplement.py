"""Phase 1 보강: 슬래시 ticker 정규화 + Nygren 추가 + 누락 ticker 가격 다운로드.

전체 collect 재실행(1.5시간) 대신 변경 부분만 처리하는 일회성 스크립트.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import yaml

from thirteen_f.collect.cusip_mapper import fill_missing
from thirteen_f.collect.edgar_client import EdgarClient, extract_13f_filings
from thirteen_f.collect.loader import (
    mark_supersedes,
    upsert_filing,
    upsert_holdings,
    upsert_manager,
)
from thirteen_f.collect.parser import parse_information_table
from thirteen_f.collect.pipeline import _info_table_filename
from thirteen_f.collect.price_loader import download_prices
from thirteen_f.core.config import load_settings


def main() -> None:
    settings = load_settings()
    conn = duckdb.connect(str(settings.duckdb_path))

    # 1) 기존 cache의 슬래시·점 ticker 정규화 (BRK/B → BRK-B)
    before = conn.execute(
        "SELECT COUNT(*) FROM cusip_ticker_map "
        "WHERE ticker IS NOT NULL AND (ticker LIKE '%/%' OR ticker LIKE '%.%')"
    ).fetchone()[0]
    conn.execute(
        "UPDATE cusip_ticker_map "
        "SET ticker = REPLACE(REPLACE(ticker, '/', '-'), '.', '-') "
        "WHERE ticker IS NOT NULL AND (ticker LIKE '%/%' OR ticker LIKE '%.%')"
    )
    print(f"[1] Normalized {before} cache ticker(s) with slash/dot")

    # 2) Nygren 처리
    managers = yaml.safe_load(Path("config/managers.yaml").read_text(encoding="utf-8"))
    nygren = next(m for m in managers if m["label"] == "Nygren")
    upsert_manager(conn, nygren)
    n_filings = 0
    n_holdings = 0
    with EdgarClient(user_agent=settings.sec_user_agent) as client:
        subs = client.get_submissions(nygren["cik"])
        filings = [
            f for f in extract_13f_filings(subs) if f["period_of_report"] >= date(2024, 1, 1)
        ]
        for f in filings:
            f["cik"] = nygren["cik"]
            upsert_filing(conn, f)
            try:
                idx = client.get_filing_index(nygren["cik"], f["accession_no"])
                fname = _info_table_filename(idx)
                if not fname:
                    continue
                xml_bytes = client.get_archive_file(nygren["cik"], f["accession_no"], fname)
                holdings = parse_information_table(xml_bytes, f["filed_at"])
                upsert_holdings(conn, f["accession_no"], holdings)
                n_filings += 1
                n_holdings += len(holdings)
            except Exception as e:
                print(f"   Failed {f['accession_no']}: {e}")
        mark_supersedes(conn, nygren["cik"])
    print(f"[2] Nygren: {n_filings} filings, {n_holdings} holdings rows")

    # 3) 새 CUSIP 매핑 (Nygren 신규 종목)
    all_cusips = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT cusip FROM holdings WHERE cusip IS NOT NULL"
        ).fetchall()
    ]
    n_resolved = fill_missing(conn, all_cusips, settings.openfigi_api_key or None)
    print(f"[3] CUSIP resolved: +{n_resolved}")

    # 4) 가격 누락 ticker만 다운로드
    missing = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT m.ticker "
            "FROM cusip_ticker_map m "
            "LEFT JOIN prices p ON m.ticker = p.ticker "
            "WHERE m.ticker IS NOT NULL AND p.ticker IS NULL "
            "ORDER BY m.ticker"
        ).fetchall()
    ]
    print(f"[4] Missing price tickers: {len(missing)}")
    results = download_prices(
        conn,
        missing,
        date(2024, 1, 1),
        Path("data/logs/failed_tickers_supplement.jsonl"),
    )
    ok = sum(1 for v in results.values() if v > 0)
    fail = sum(1 for v in results.values() if v == 0)
    print(f"    Downloaded: {ok}, Failed: {fail}")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()

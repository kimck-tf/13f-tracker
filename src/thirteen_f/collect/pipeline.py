"""Phase 1 orchestration: resolve_cik → fetch filings → parse → upsert → CUSIP map → prices."""
from __future__ import annotations

import json
import logging
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
from thirteen_f.collect.price_loader import download_prices
from thirteen_f.collect.resolve_cik import resolve_missing_ciks
from thirteen_f.core.config import Settings

logger = logging.getLogger(__name__)


def _info_table_filename(filing_index: dict) -> str | None:
    """filing index.json에서 information table XML 파일명 식별.
    보통 *infoTable*.xml 또는 *info_table*.xml.
    """
    items = filing_index.get("directory", {}).get("item", [])
    for it in items:
        name = it.get("name", "")
        if name.endswith(".xml") and "infotable" in name.lower().replace("_", ""):
            return name
    # 폴백: .xml 중 form13f가 들어간 것
    for it in items:
        name = it.get("name", "")
        if name.endswith(".xml") and "13f" in name.lower():
            return name
    return None


def run_collect(
    settings: Settings,
    managers_yaml: Path,
    db_path: Path,
    start_date: date,
    failure_log: Path | None = None,
) -> dict[str, int]:
    """Phase 1 전체 실행. 통계 dict 반환.

    1. Resolve missing CIKs
    2. For each manager: fetch submissions, extract 13F filings, parse, upsert
    3. mark_supersedes
    4. CUSIP fill_missing
    5. Download prices for unique tickers
    """
    stats: dict[str, int] = {
        "managers": 0,
        "filings_parsed": 0,
        "holdings_rows": 0,
        "cusip_resolved": 0,
        "price_tickers": 0,
    }

    conn = duckdb.connect(str(db_path))
    try:
        with EdgarClient(user_agent=settings.sec_user_agent) as client:
            # 1) Resolve CIK
            tickers_json = client.get_company_tickers()
            n_resolved = resolve_missing_ciks(managers_yaml, tickers_json)
            logger.info("Resolved %d missing CIKs", n_resolved)

            # 2) Reload yaml after resolve
            managers = yaml.safe_load(managers_yaml.read_text(encoding="utf-8"))
            for m in managers:
                if not m.get("cik"):
                    logger.warning("Skip %s (no CIK)", m.get("label"))
                    continue
                upsert_manager(conn, m)
                stats["managers"] += 1

                # 3) Fetch 13F filings
                subs = client.get_submissions(m["cik"])
                filings = extract_13f_filings(subs)
                filings = [f for f in filings if f["period_of_report"] >= start_date]
                for f in filings:
                    f["cik"] = m["cik"]
                    upsert_filing(conn, f)
                    # 4) Parse info table
                    try:
                        idx = client.get_filing_index(m["cik"], f["accession_no"])
                        fname = _info_table_filename(idx)
                        if not fname:
                            logger.warning(
                                "No info table XML for %s/%s", m["label"], f["accession_no"]
                            )
                            continue
                        xml_bytes = client.get_archive_file(m["cik"], f["accession_no"], fname)
                        holdings = parse_information_table(xml_bytes, f["filed_at"])
                        upsert_holdings(conn, f["accession_no"], holdings)
                        stats["holdings_rows"] += len(holdings)
                        stats["filings_parsed"] += 1
                    except Exception as e:
                        logger.exception("Failed parsing %s/%s: %s", m["label"], f["accession_no"], e)

                mark_supersedes(conn, m["cik"])

            # 5) CUSIP fill missing
            all_cusips = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT cusip FROM holdings WHERE cusip IS NOT NULL"
                ).fetchall()
            ]
            stats["cusip_resolved"] = fill_missing(conn, all_cusips, settings.openfigi_api_key or None)

            # 6) Prices
            tickers = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL"
                ).fetchall()
            ]
            stats["price_tickers"] = len(tickers)
            price_results = download_prices(conn, tickers, start_date, failure_log)
            n_failed = sum(1 for v in price_results.values() if v == 0)
            logger.info("Prices: %d tickers downloaded, %d failed", len(tickers) - n_failed, n_failed)

    finally:
        conn.close()
    return stats

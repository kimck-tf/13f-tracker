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
    remove_filing,
    upsert_filing,
    upsert_holdings,
    upsert_manager,
)
from thirteen_f.collect.parser import parse_amendment_type, parse_information_table
from thirteen_f.collect.price_loader import download_prices
from thirteen_f.collect.resolve_cik import resolve_missing_ciks
from thirteen_f.core.config import Settings

logger = logging.getLogger(__name__)


def _info_table_filename(filing_index: dict) -> str | None:
    """filing index.json에서 information table XML 파일명 식별.

    13F-HR 제출물의 XML은 표지(primary_doc.xml)와 information table이다. 표 파일명은
    제출 대행사마다 달라(infotable.xml, informationtable.xml, 56757.xml 같은 숫자 이름)
    이름 규칙 대신 primary_doc.xml이 아닌 XML을 고른다. 여러 개면 이름에 'table'이 든
    것, 없으면 가장 큰 파일. primary_doc.xml뿐이면(13F-NT 등) None.
    """
    items = filing_index.get("directory", {}).get("item", [])
    xmls = [
        it for it in items
        if it.get("name", "").lower().endswith(".xml")
        and it.get("name", "").lower() != "primary_doc.xml"
    ]
    if not xmls:
        return None
    for it in xmls:
        if "table" in it["name"].lower():
            return it["name"]
    return max(xmls, key=lambda it: int(it.get("size") or 0))["name"]


def _is_new_holdings_amendment(client: EdgarClient, cik: str, accession_no: str) -> bool:
    """13F-HR/A 표지의 amendmentType이 NEW HOLDINGS인지. 표지를 못 읽으면 False(정정본 취급)."""
    try:
        doc = client.get_archive_file(cik, accession_no, "primary_doc.xml")
        return parse_amendment_type(doc) == "NEW HOLDINGS"
    except Exception as e:
        logger.warning(
            "Amendment type unknown for %s (treated as restatement): %s", accession_no, e
        )
        return False


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

                # 3) Fetch 13F filings — 운용 법인이 바뀐 매니저는 extra_ciks의 제출분도 수집해
                #    대표 CIK(m["cik"])로 저장한다 (분석·전략이 cik 단위로 분기를 이어 붙이므로).
                #    EDGAR 원문 경로는 실제 제출자 CIK(filer_cik)를 쓴다.
                primary_periods: set[date] = set()
                for i, filer_cik in enumerate([m["cik"], *(m.get("extra_ciks") or [])]):
                    subs = client.get_submissions(filer_cik)
                    filings = extract_13f_filings(subs)
                    filings = [f for f in filings if f["period_of_report"] >= start_date]
                    if i == 0:
                        primary_periods = {f["period_of_report"] for f in filings}
                    for f in filings:
                        f["cik"] = m["cik"]
                        if i > 0 and f["period_of_report"] in primary_periods:
                            # 대표 CIK도 보고한 분기면 대표 CIK 제출분을 쓴다 — 추가 법인의 부분
                            # 보고(예: Pershing Square Inc.의 HHH 단독분)가 같은 날 제출돼 전체
                            # 포트폴리오를 가리지 않게. 이전 실행이 저장한 것도 지운다.
                            remove_filing(conn, f["accession_no"])
                            continue
                        if f["is_amendment"] and _is_new_holdings_amendment(
                            client, filer_cik, f["accession_no"]
                        ):
                            # 추가 공개분만 담은 정정은 원본을 대체하지 않는다 → 적재하지 않아
                            # 원본이 유효본으로 남게 한다 (Spec §5.2). 이전 실행분이 있으면 삭제.
                            remove_filing(conn, f["accession_no"])
                            logger.info(
                                "Skip NEW HOLDINGS amendment %s/%s", m["label"], f["accession_no"]
                            )
                            continue
                        upsert_filing(conn, f)
                        # 4) Parse info table
                        try:
                            idx = client.get_filing_index(filer_cik, f["accession_no"])
                            fname = _info_table_filename(idx)
                            if not fname:
                                logger.warning(
                                    "No info table XML for %s/%s", m["label"], f["accession_no"]
                                )
                                continue
                            xml_bytes = client.get_archive_file(
                                filer_cik, f["accession_no"], fname
                            )
                            holdings = parse_information_table(xml_bytes, f["filed_at"])
                            upsert_holdings(conn, f["accession_no"], holdings)
                            stats["holdings_rows"] += len(holdings)
                            stats["filings_parsed"] += 1
                        except Exception as e:
                            logger.exception(
                                "Failed parsing %s/%s: %s", m["label"], f["accession_no"], e
                            )

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

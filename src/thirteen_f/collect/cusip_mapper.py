"""CUSIP → ticker mapping via OpenFIGI with DuckDB cache. Spec §5.1-1e."""
from __future__ import annotations

import logging
import time
from typing import Any

import duckdb
import httpx

logger = logging.getLogger(__name__)

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
# OpenFIGI v3 batch 한도: 무인증 10 jobs/batch, 인증 100 jobs/batch (초과 시 413 Payload Too Large)
OPENFIGI_BATCH_SIZE_UNAUTHED = 10
OPENFIGI_BATCH_SIZE_AUTHED = 100
OPENFIGI_RATE_LIMIT_SEC = 60.0 / 25.0  # 키 없을 때 25/min
OPENFIGI_RATE_LIMIT_SEC_AUTHED = 60.0 / 250.0  # 키 있을 때 250/min

# OpenFIGI exchCode 중 US primary listing 식별자. 그 외(GZ, XH, XF 등 외국·secondary)는
# yfinance가 인식할 수 없으므로 ticker=None으로 둠 (CUSIP을 fallback 키로 사용).
US_PRIMARY_EXCH_CODES = frozenset({
    "US",  # 미국 composite
    "UN",  # NYSE
    "UQ",  # NASDAQ GS
    "UR",  # NASDAQ GM
    "UP",  # NASDAQ CM
    "UW",  # NASDAQ Capital
    "UA",  # NYSE American (AMEX)
    "UF",  # NYSE Arca
    "UV",  # OTC US
    "UD",  # OTC BB
})


def _pick_us_primary(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    """OpenFIGI data[] 중 US primary 거래소 첫 항목 선택. 없으면 None."""
    for item in data:
        if item.get("exchCode") in US_PRIMARY_EXCH_CODES:
            return item
    return None


def fetch_cache(
    conn: duckdb.DuckDBPyConnection, cusips: list[str]
) -> dict[str, dict[str, Any]]:
    if not cusips:
        return {}
    placeholders = ",".join("?" for _ in cusips)
    rows = conn.execute(
        f"SELECT cusip, ticker, figi, name, is_etf FROM cusip_ticker_map "
        f"WHERE cusip IN ({placeholders})",
        cusips,
    ).fetchall()
    return {
        r[0]: {"cusip": r[0], "ticker": r[1], "figi": r[2], "name": r[3], "is_etf": r[4]}
        for r in rows
    }


def upsert_mapping(
    conn: duckdb.DuckDBPyConnection, mappings: list[dict[str, Any]]
) -> None:
    if not mappings:
        return
    conn.executemany(
        """
        INSERT INTO cusip_ticker_map (cusip, ticker, figi, name, is_etf)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (cusip) DO UPDATE SET
            ticker=excluded.ticker,
            figi=excluded.figi,
            name=excluded.name,
            is_etf=excluded.is_etf,
            updated_at=now()
        """,
        [
            (m["cusip"], m.get("ticker"), m.get("figi"), m.get("name"), m.get("is_etf"))
            for m in mappings
        ],
    )


def _openfigi_batch(
    cusips: list[str], api_key: str | None
) -> list[dict[str, Any]]:
    """Call OpenFIGI /v3/mapping for a batch of CUSIPs."""
    headers = {"Content-Type": "text/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    payload = [{"idType": "ID_CUSIP", "idValue": c} for c in cusips]
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(OPENFIGI_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    out: list[dict[str, Any]] = []
    for cusip, entry in zip(cusips, data):
        if "data" not in entry or not entry["data"]:
            out.append(
                {"cusip": cusip, "ticker": None, "figi": None, "name": None, "is_etf": False}
            )
            continue
        items = entry["data"]
        us = _pick_us_primary(items)
        if us is None:
            # 외국 거래소·secondary listing뿐 — ticker None으로 두고 figi/name은 first
            # item에서 (compositeFIGI 우선) 가져와 식별 정보는 유지.
            first = items[0]
            out.append({
                "cusip": cusip,
                "ticker": None,
                "figi": first.get("compositeFIGI") or first.get("figi"),
                "name": first.get("name"),
                "is_etf": False,
            })
            continue
        sec_type = (us.get("securityType") or us.get("securityType2") or "").lower()
        is_etf = "etf" in sec_type or "etp" in sec_type
        out.append(
            {
                "cusip": cusip,
                "ticker": us.get("ticker"),
                "figi": us.get("compositeFIGI") or us.get("figi"),
                "name": us.get("name"),
                "is_etf": is_etf,
            }
        )
    return out


def fill_missing(
    conn: duckdb.DuckDBPyConnection,
    cusips: list[str],
    api_key: str | None = None,
) -> int:
    """캐시 미스인 CUSIP만 OpenFIGI 호출. 적재된 매핑 수 반환."""
    unique = sorted(set(cusips))
    cached = fetch_cache(conn, unique)
    misses = [c for c in unique if c not in cached]
    if not misses:
        logger.info("CUSIP mapping: all %d CUSIPs cached, no API calls.", len(unique))
        return 0

    logger.info("CUSIP mapping: %d misses, calling OpenFIGI…", len(misses))
    interval = OPENFIGI_RATE_LIMIT_SEC_AUTHED if api_key else OPENFIGI_RATE_LIMIT_SEC
    batch_size = OPENFIGI_BATCH_SIZE_AUTHED if api_key else OPENFIGI_BATCH_SIZE_UNAUTHED
    inserted = 0
    for i in range(0, len(misses), batch_size):
        batch = misses[i : i + batch_size]
        results = _openfigi_batch(batch, api_key)
        upsert_mapping(conn, results)
        inserted += len(results)
        if i + batch_size < len(misses):
            time.sleep(interval)
    return inserted

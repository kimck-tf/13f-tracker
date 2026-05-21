"""DuckDB upsert helpers. Spec §5.1-1g, §5.2 정정본 정책."""
from __future__ import annotations

import logging
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


def upsert_manager(conn: duckdb.DuckDBPyConnection, m: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO managers (cik, name, label, fund, style, active_since, cloning_score_weight)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (cik) DO UPDATE SET
            name=excluded.name, label=excluded.label, fund=excluded.fund,
            style=excluded.style, active_since=excluded.active_since,
            cloning_score_weight=excluded.cloning_score_weight
        """,
        (
            m["cik"], m["name"], m.get("label"), m.get("fund"),
            m.get("style"), m.get("active_since"), m.get("cloning_score_weight", 1.0),
        ),
    )


def upsert_filing(conn: duckdb.DuckDBPyConnection, f: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO filings (accession_no, cik, form_type, period_of_report, filed_at, is_amendment, superseded_by)
        VALUES (?, ?, ?, ?, ?, ?, NULL)
        ON CONFLICT (accession_no) DO UPDATE SET
            form_type=excluded.form_type,
            period_of_report=excluded.period_of_report,
            filed_at=excluded.filed_at,
            is_amendment=excluded.is_amendment
        """,
        (
            f["accession_no"], f["cik"], f["form_type"],
            f["period_of_report"], f["filed_at"], f.get("is_amendment", False),
        ),
    )


def upsert_holdings(
    conn: duckdb.DuckDBPyConnection, accession_no: str, holdings: list[dict[str, Any]]
) -> None:
    if not holdings:
        return
    # 13F XML이 동일 (cusip, title_of_class, put_call) 조합을 voting authority /
    # investmentDiscretion 별로 분할 보고하는 경우가 있음. PK는 (accession, cusip, class,
    # put_call) 이므로 미리 SUM(shares, value_usd) 집계해 PK 충돌을 방지.
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for h in holdings:
        key = (h["cusip"], h.get("title_of_class") or "", h.get("put_call") or "")
        if key in agg:
            agg[key]["value_usd"] = (agg[key].get("value_usd") or 0) + (h.get("value_usd") or 0)
            agg[key]["shares"] = (agg[key].get("shares") or 0) + (h.get("shares") or 0)
        else:
            agg[key] = {
                "name_of_issuer": h.get("name_of_issuer"),
                "value_usd": h.get("value_usd"),
                "shares": h.get("shares"),
                "share_type": h.get("share_type"),
            }
    # 동일 accession_no 재적재 시 기존 행 모두 삭제 후 재삽입 (idempotent)
    conn.execute("DELETE FROM holdings WHERE accession_no = ?", (accession_no,))
    rows = [
        (
            accession_no,
            cusip,
            v["name_of_issuer"],
            cls,
            v["value_usd"],
            v["shares"],
            v["share_type"],
            put_call,
        )
        for (cusip, cls, put_call), v in agg.items()
    ]
    conn.executemany(
        """
        INSERT INTO holdings (accession_no, cusip, name_of_issuer, title_of_class,
                              value_usd, shares, share_type, put_call)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def mark_supersedes(conn: duckdb.DuckDBPyConnection, cik: str) -> int:
    """Spec §5.2: 같은 (cik, period_of_report) 내 최신 filed_at 외 모두 superseded_by 마킹.
    최신 항목은 superseded_by=NULL 유지.
    """
    # 1. 모든 (cik, period) 그룹의 최신 accession 식별 (latest_acc) + 같은 그룹의 모든 accession (acc)
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT accession_no, period_of_report,
                   ROW_NUMBER() OVER (
                       PARTITION BY period_of_report
                       ORDER BY filed_at DESC, accession_no DESC
                   ) AS rn,
                   FIRST_VALUE(accession_no) OVER (
                       PARTITION BY period_of_report
                       ORDER BY filed_at DESC, accession_no DESC
                   ) AS latest_acc
            FROM filings
            WHERE cik = ?
        )
        SELECT accession_no, rn, latest_acc FROM ranked
        """,
        (cik,),
    ).fetchall()

    # 2. 각 행에 대해 명시적 superseded_by 값 결정: rn==1이면 NULL, 그 외엔 latest_acc
    updates: list[tuple[str | None, str]] = []
    for acc, rn, latest_acc in rows:
        updates.append((None if rn == 1 else latest_acc, acc))

    if not updates:
        # cik에 해당하는 filing이 0개일 때 (start_date 필터 이후 미보고 등) DuckDB
        # executemany는 빈 리스트로 호출 시 InvalidInputException — early return.
        return 0

    conn.executemany(
        "UPDATE filings SET superseded_by = ? WHERE accession_no = ?",
        updates,
    )
    return sum(1 for sb, _ in updates if sb is not None)

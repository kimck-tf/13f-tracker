"""새 13F-HR 감지 — collect가 아직 적재하지 않은 원본 제출을 EDGAR submissions에서 찾는다."""
from __future__ import annotations

from datetime import date

import duckdb

from thirteen_f.collect.edgar_client import EdgarClient, extract_13f_filings


def find_new_filings(
    conn: duckdb.DuckDBPyConnection, client: EdgarClient, managers: list[dict]
) -> list[dict]:
    """DB `filings`에 없는 13F-HR 원본을 filed_at 오름차순으로 반환.

    collect가 적재할 것만 센다: DB의 최소 분기 이후(DB가 비면 전부)이고, 정정본(13F-HR/A)은
    뒤따르는 collect가 원본과 함께 처리하므로 뺀다. extra_ciks 제출분 중 대표 CIK도 보고한
    분기는 collect가 적재하지 않으므로(`pipeline.run_collect`) 세지 않는다 — 세면 매일 새
    공시로 잡힌다.
    """
    row = conn.execute("SELECT MIN(period_of_report) FROM filings").fetchone()
    first: date | None = row[0] if row else None
    known = {r[0] for r in conn.execute("SELECT accession_no FROM filings").fetchall()}
    out: list[dict] = []
    for m in managers:
        if not m.get("cik"):
            continue
        primary_periods: set[date] = set()
        for i, filer_cik in enumerate([m["cik"], *(m.get("extra_ciks") or [])]):
            filings = [
                f for f in extract_13f_filings(client.get_submissions(filer_cik))
                if first is None or f["period_of_report"] >= first
            ]
            if i == 0:
                primary_periods = {f["period_of_report"] for f in filings}
            for f in filings:
                if f["form_type"] != "13F-HR" or f["accession_no"] in known:
                    continue
                if i > 0 and f["period_of_report"] in primary_periods:
                    continue
                out.append({
                    "label": m["label"],
                    "filer_cik": filer_cik,
                    "accession_no": f["accession_no"],
                    "period_of_report": f["period_of_report"],
                    "filed_at": f["filed_at"],
                })
    return sorted(out, key=lambda n: n["filed_at"])

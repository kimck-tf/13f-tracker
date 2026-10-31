"""`find_new_filings` — collect가 아직 적재하지 않은 13F-HR 원본을 찾는다 (check-filings)."""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.init_db import init_db
from thirteen_f.collect.watch import find_new_filings

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "edgar" / "submissions_buffett.json"


def _cover(amendment_type: str) -> bytes:
    return (
        b'<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/thirteenffiler">'
        b"<formData><coverPage><amendmentInfo><amendmentType>"
        + amendment_type.encode()
        + b"</amendmentType></amendmentInfo></coverPage></formData></edgarSubmission>"
    )


class FakeClient:
    """CIK별 submissions를 돌려준다. 지정하지 않은 CIK는 Buffett fixture.
    정정본 표지는 covers에 없으면 NEW HOLDINGS(추가분만 담은 정정)."""

    def __init__(self, subs: dict | None = None, covers: dict | None = None):
        self.calls: list[str] = []
        self.subs = subs or {}
        self.covers = covers or {}

    def get_submissions(self, cik):
        self.calls.append(cik)
        return self.subs.get(cik) or json.loads(FIXTURE.read_text(encoding="utf-8"))

    def get_archive_file(self, cik, accession_no, filename):
        return self.covers.get(accession_no, _cover("NEW HOLDINGS"))


def _subs(*rows: tuple[str, str, str, str]) -> dict:
    """rows: (accession, form, filingDate, reportDate)."""
    accs, forms, filed, report = zip(*rows, strict=True)
    recent = {
        "accessionNumber": list(accs),
        "form": list(forms),
        "filingDate": list(filed),
        "reportDate": list(report),
    }
    return {"filings": {"recent": recent}}


def _conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    return duckdb.connect(str(db))


def _store(c, accession: str, period: str, filed: str) -> None:
    c.execute("INSERT OR IGNORE INTO managers (cik, name) VALUES ('0001067983', 'B')")
    c.execute(
        "INSERT INTO filings VALUES (?, '0001067983', '13F-HR', ?, ?, FALSE, NULL)",
        [accession, period, filed],
    )


def test_reports_only_original_13f_hr_not_in_db(tmp_path):
    c = _conn(tmp_path)
    managers = [
        {"label": "Buffett", "cik": "0001067983", "extra_ciks": ["0002026053"]},
        {"label": "NoCik", "cik": None},
    ]
    client = FakeClient()
    new = find_new_filings(c, client, managers)
    assert client.calls == ["0001067983", "0002026053"]  # CIK 없는 매니저는 collect처럼 건너뛴다
    # 13F-HR 원본 2건을 filed_at 순으로 — NEW HOLDINGS 정정(…16)·10-K(…14)는 빼고, extra CIK가 같은
    # 분기에 낸 것(fixture가 같아 전부)도 뺀다
    assert [n["accession_no"] for n in new] == ["0001067983-24-000015", "0001067983-24-000017"]
    assert all(n["label"] == "Buffett" and n["filer_cik"] == "0001067983" for n in new)
    assert [str(n["period_of_report"]) for n in new] == ["2023-12-31", "2024-03-31"]


def test_extra_cik_filings_count_only_for_periods_the_primary_cik_did_not_report(tmp_path):
    """collect는 대표 CIK도 보고한 분기의 extra_ciks 제출분을 적재하지 않는다 — 그것을 새 공시로
    세면 check-filings가 매일 exit 1을 낸다 (Ackman: Pershing Square 두 법인이 같은 분기를 제출)."""
    c = _conn(tmp_path)
    client = FakeClient({
        "0001336528": _subs(("p-25-1", "13F-HR", "2025-11-14", "2025-09-30")),
        "0002026053": _subs(
            ("x-25-1", "13F-HR", "2025-11-14", "2025-09-30"),
            ("x-26-1", "13F-HR", "2026-08-14", "2026-06-30"),
        ),
    })
    managers = [{"label": "Ackman", "cik": "0001336528", "extra_ciks": ["0002026053"]}]
    new = find_new_filings(c, client, managers)
    assert [(n["accession_no"], n["filer_cik"]) for n in new] == [
        ("p-25-1", "0001336528"),
        ("x-26-1", "0002026053"),
    ]


def test_filings_already_in_db_are_skipped(tmp_path):
    c = _conn(tmp_path)
    _store(c, "0001067983-24-000015", "2023-12-31", "2024-02-14")
    new = find_new_filings(c, FakeClient(), [{"label": "Buffett", "cik": "0001067983"}])
    assert [n["accession_no"] for n in new] == ["0001067983-24-000017"]


def test_filings_before_the_db_first_quarter_are_ignored(tmp_path):
    """DB가 2024Q1부터면 2023Q4 원본(…15)은 collect 범위 밖이라 새 공시가 아니다."""
    c = _conn(tmp_path)
    _store(c, "0001067983-24-000017", "2024-03-31", "2024-05-15")
    assert find_new_filings(c, FakeClient(), [{"label": "Buffett", "cik": "0001067983"}]) == []


def test_restatements_count_but_new_holdings_amendments_do_not(tmp_path):
    """collect는 원본을 대체하는 정정본(RESTATEMENT)을 적재하고, 추가분만 담은 NEW HOLDINGS 정정본은
    적재하지 않는다 — 감지도 같게 (Li Lu 2025Q4: 기한 이틀 뒤 원본을 대체한 정정본)."""
    c = _conn(tmp_path)
    _store(c, "orig-1", "2025-12-31", "2026-02-17")
    client = FakeClient(
        {
            "0001067983": _subs(
                ("orig-1", "13F-HR", "2026-02-17", "2025-12-31"),
                ("amend-r", "13F-HR/A", "2026-02-19", "2025-12-31"),
                ("amend-n", "13F-HR/A", "2026-02-20", "2025-12-31"),
            )
        },
        covers={"amend-r": _cover("RESTATEMENT")},
    )
    new = find_new_filings(c, client, [{"label": "Buffett", "cik": "0001067983"}])
    assert [(n["accession_no"], n["form_type"]) for n in new] == [("amend-r", "13F-HR/A")]

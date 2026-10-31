from datetime import date
from unittest.mock import patch

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.pipeline import _info_table_filename, run_collect
from thirteen_f.core.config import Settings


def _index(*files: tuple[str, str]) -> dict:
    """EDGAR filing index.json의 directory.item 구조 (name, size)."""
    return {"directory": {"item": [{"name": n, "size": s} for n, s in files]}}


COMMON = (("0001-index-headers.html", ""), ("0001-index.html", ""), ("0001.txt", ""))


def test_numeric_info_table_name():
    """Berkshire 제출물처럼 information table이 숫자 이름(56757.xml)인 경우."""
    idx = _index(*COMMON, ("56757.xml", "44724"), ("primary_doc.xml", "5555"))
    assert _info_table_filename(idx) == "56757.xml"


def test_informationtable_name():
    """'informationtable'에는 'infotable' 부분 문자열이 없다."""
    idx = _index(*COMMON, ("informationtable.xml", "6669"), ("primary_doc.xml", "2980"))
    assert _info_table_filename(idx) == "informationtable.xml"


def test_infotable_name_still_matches():
    idx = _index(*COMMON, ("primary_doc.xml", "3000"), ("form13fInfoTable.xml", "9000"))
    assert _info_table_filename(idx) == "form13fInfoTable.xml"


def test_notice_filing_without_info_table_returns_none():
    """13F-NT·표 없는 제출물은 primary_doc.xml만 있다."""
    idx = _index(*COMMON, ("primary_doc.xml", "2500"))
    assert _info_table_filename(idx) is None


INFO_TABLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip>
    <value>1000</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


class FakeEdgar:
    """제출 법인별 13F-HR 목록 {cik: [(accession, period, filed), ...]}을 돌려주는 가짜 EDGAR."""

    def __init__(self, filings=None):
        self.filings = filings or {
            "0000000001": [("acc-old", "2026-03-31", "2026-05-15")],
            "0000000002": [("acc-new", "2026-06-30", "2026-08-14")],
        }
        self.archive_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_company_tickers(self):
        return {}

    def get_submissions(self, cik):
        rows = self.filings[cik]
        return {"filings": {"recent": {"accessionNumber": [r[0] for r in rows],
                                       "form": ["13F-HR"] * len(rows),
                                       "filingDate": [r[2] for r in rows],
                                       "reportDate": [r[1] for r in rows]}}}

    def get_filing_index(self, cik, accession_no):
        return _index(("primary_doc.xml", "100"), ("table.xml", "900"))

    def get_archive_file(self, cik, accession_no, filename):
        self.archive_calls.append((cik, accession_no))
        return INFO_TABLE


def test_run_collect_stores_extra_cik_filings_under_manager_cik(tmp_path):
    """운용 법인이 바뀐 매니저(예: Ackman → Pershing Square Inc.)는 extra_ciks 제출분도
    대표 CIK로 저장해 분기 연속성을 지킨다. 원문은 실제 제출자 CIK 경로에서 받는다."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    managers_yaml = tmp_path / "managers.yaml"
    managers_yaml.write_text(
        "- name: A\n  label: A\n  cik: '0000000001'\n  extra_ciks: ['0000000002']\n",
        encoding="utf-8",
    )
    fake = FakeEdgar()
    with patch("thirteen_f.collect.pipeline.EdgarClient", return_value=fake), \
         patch("thirteen_f.collect.pipeline.fill_missing", return_value=0), \
         patch("thirteen_f.collect.pipeline.download_prices", return_value={}):
        run_collect(Settings(sec_user_agent="ua", openfigi_api_key="", duckdb_path=db),
                    managers_yaml, db, date(2024, 1, 1))

    conn = duckdb.connect(str(db))
    assert conn.execute("SELECT accession_no, cik FROM filings ORDER BY 1").fetchall() == [
        ("acc-new", "0000000001"), ("acc-old", "0000000001"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0] == 2
    conn.close()
    assert ("0000000002", "acc-new") in fake.archive_calls


def test_extra_cik_filing_ignored_for_period_reported_by_primary_cik(tmp_path):
    """같은 분기를 대표 CIK도 보고했으면 대표 CIK 제출분을 쓴다. Pershing Square Inc.는
    2025Q2~2026Q1에 HHH 한 종목짜리 13F를 같은 날 따로 냈고, '늦게 제출된 1건만 유효'
    규칙 때문에 기존 법인의 전체 포트폴리오를 가렸다. 이전 실행이 저장한 것도 지운다."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    managers_yaml = tmp_path / "managers.yaml"
    managers_yaml.write_text(
        "- name: A\n  label: A\n  cik: '0000000001'\n  extra_ciks: ['0000000002']\n",
        encoding="utf-8",
    )
    fake = FakeEdgar({
        "0000000001": [("acc-002336", "2026-03-31", "2026-05-15")],
        "0000000002": [("acc-002339", "2026-03-31", "2026-05-15"),
                       ("acc-003790", "2026-06-30", "2026-08-14")],
    })
    settings = Settings(sec_user_agent="ua", openfigi_api_key="", duckdb_path=db)
    with patch("thirteen_f.collect.pipeline.EdgarClient", return_value=fake), \
         patch("thirteen_f.collect.pipeline.fill_missing", return_value=0), \
         patch("thirteen_f.collect.pipeline.download_prices", return_value={}):
        run_collect(settings, managers_yaml, db, date(2024, 1, 1))
        # 수정 전 로직으로 저장된 적이 있어도 다시 실행하면 정리돼야 한다
        conn = duckdb.connect(str(db))
        conn.execute("INSERT OR IGNORE INTO filings VALUES ('acc-002339', '0000000001', '13F-HR', "
                     "DATE '2026-03-31', DATE '2026-05-15', FALSE, NULL)")
        conn.close()
        run_collect(settings, managers_yaml, db, date(2024, 1, 1))

    conn = duckdb.connect(str(db))
    assert conn.execute(
        "SELECT accession_no FROM filings WHERE superseded_by IS NULL ORDER BY 1"
    ).fetchall() == [("acc-002336",), ("acc-003790",)]
    assert conn.execute(
        "SELECT COUNT(*) FROM filings WHERE accession_no = 'acc-002339'"
    ).fetchone()[0] == 0
    conn.close()


THOUSANDS_TABLE = (
    b'<?xml version="1.0" encoding="UTF-8"?><informationTable '
    b'xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
    + b"".join(
        b"<infoTable><nameOfIssuer>C%d</nameOfIssuer><titleOfClass>COM</titleOfClass>"
        b"<cusip>C0000000%d</cusip><value>1</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>"
        b"<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>" % (i, i)
        for i in range(5)
    )
    + b"</informationTable>"
)
YAML_A = "- name: A\n  label: A\n  cik: '0000000001'\n"
YAML_B = "- name: B\n  label: B\n  cik: '0000000009'\n"


class ThousandsEdgar(FakeEdgar):
    """금액을 천 달러로 낸 13F-HR 하나(5행, 각 10주 × 종가 100 = $1,000인데 value 1)."""

    def __init__(self):
        super().__init__({"0000000001": [("acc-k", "2026-03-31", "2026-05-15")]})

    def get_archive_file(self, cik, accession_no, filename):
        return THOUSANDS_TABLE


def _thousands_db(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)",
        [(f"C0000000{i}", f"T{i}") for i in range(5)],
    )
    c.executemany(
        "INSERT INTO prices VALUES (?, DATE '2026-03-31', 100, 100, 100, 100, 100, 1)",
        [(f"T{i}",) for i in range(5)],
    )
    c.close()
    managers_yaml = tmp_path / "managers.yaml"
    managers_yaml.write_text(YAML_A, encoding="utf-8")
    return db, managers_yaml


def _values(db):
    conn = duckdb.connect(str(db))
    rows = conn.execute("SELECT DISTINCT value_usd FROM holdings WHERE accession_no = 'acc-k'")
    out = sorted(r[0] for r in rows.fetchall())
    conn.close()
    return out


def _collect(db, managers_yaml, fill_missing_error=None):
    settings = Settings(sec_user_agent="ua", openfigi_api_key="", duckdb_path=db)
    if fill_missing_error is None:
        fm = patch("thirteen_f.collect.pipeline.fill_missing", return_value=0)
    else:
        fm = patch("thirteen_f.collect.pipeline.fill_missing", side_effect=fill_missing_error)
    with (
        patch("thirteen_f.collect.pipeline.EdgarClient", return_value=ThousandsEdgar()),
        fm,
        patch("thirteen_f.collect.pipeline.download_prices", return_value={}),
    ):
        run_collect(settings, managers_yaml, db, date(2024, 1, 1))


def test_a_failure_after_parsing_keeps_the_thousand_unit_fix(tmp_path):
    """collect는 범위 안 필링을 매번 다시 파싱해 천 달러 원값으로 되돌린다. 뒤의 OpenFIGI 단계가
    실패해도(429) 이미 보정된 필링이 1/1000로 남으면 안 된다."""
    db, managers_yaml = _thousands_db(tmp_path)
    _collect(db, managers_yaml)
    assert _values(db) == [1000]
    with pytest.raises(RuntimeError):
        _collect(db, managers_yaml, fill_missing_error=RuntimeError("OpenFIGI 429"))
    assert _values(db) == [1000]


def test_a_failure_inside_the_manager_loop_rolls_back_the_reparse(tmp_path):
    """매니저 루프 도중 실패하면(다음 매니저의 EDGAR 요청) 이미 다시 파싱한 필링도 실행 전
    값으로 돌아간다."""
    db, managers_yaml = _thousands_db(tmp_path)
    _collect(db, managers_yaml)
    managers_yaml.write_text(YAML_A + YAML_B, encoding="utf-8")
    with pytest.raises(KeyError):  # 가짜 EDGAR에 B의 제출 목록이 없다
        _collect(db, managers_yaml)
    assert _values(db) == [1000]

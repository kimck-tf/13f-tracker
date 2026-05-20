import json
from datetime import date
from pathlib import Path

from thirteen_f.collect.edgar_client import extract_13f_filings


FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "edgar" / "submissions_buffett.json"


def test_extract_13f_only():
    submissions = json.loads(FIXTURE.read_text())
    filings = extract_13f_filings(submissions)
    forms = [f["form_type"] for f in filings]
    # 13F-HR, 13F-HR/A 포함, 10-K 제외
    assert "10-K" not in forms
    assert forms.count("13F-HR") == 2
    assert forms.count("13F-HR/A") == 1


def test_filing_fields():
    submissions = json.loads(FIXTURE.read_text())
    filings = extract_13f_filings(submissions)
    f0 = filings[0]
    assert f0["accession_no"] == "0001067983-24-000017"
    assert f0["form_type"] == "13F-HR"
    assert f0["period_of_report"] == date(2024, 3, 31)
    assert f0["filed_at"] == date(2024, 5, 15)
    assert f0["is_amendment"] is False


def test_amendment_flag():
    submissions = json.loads(FIXTURE.read_text())
    filings = extract_13f_filings(submissions)
    amendment = [f for f in filings if f["form_type"] == "13F-HR/A"][0]
    assert amendment["is_amendment"] is True

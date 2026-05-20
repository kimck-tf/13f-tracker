from datetime import date
from pathlib import Path

from thirteen_f.collect.parser import parse_information_table, normalize_value


FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "edgar"


def test_normalize_value_old_unit():
    # filed_at < 2023-01-03 → ×1000
    assert normalize_value("1000", date(2022, 11, 15)) == 1_000_000


def test_normalize_value_new_unit():
    # filed_at >= 2023-01-03 → 그대로
    assert normalize_value("1000000", date(2023, 2, 14)) == 1_000_000


def test_normalize_value_boundary():
    # 2023-01-03 정확히 = 신규 단위 (>= 적용)
    assert normalize_value("1000000", date(2023, 1, 3)) == 1_000_000
    assert normalize_value("1000", date(2023, 1, 2)) == 1_000_000


def test_parse_information_table_old_unit():
    xml_bytes = (FIXTURES / "info_table_old_unit.xml").read_bytes()
    rows = parse_information_table(xml_bytes, filed_at=date(2022, 11, 15))
    assert len(rows) == 2
    apple = rows[0]
    assert apple["cusip"] == "037833100"
    assert apple["name_of_issuer"] == "APPLE INC"
    assert apple["title_of_class"] == "COM"
    assert apple["value_usd"] == 1_000_000_000  # 1,000,000 × 1000
    assert apple["shares"] == 10000
    assert apple["share_type"] == "SH"
    assert apple["put_call"] == ""  # NULL 회피, 빈 문자열


def test_parse_information_table_put_call():
    xml_bytes = (FIXTURES / "info_table_old_unit.xml").read_bytes()
    rows = parse_information_table(xml_bytes, filed_at=date(2022, 11, 15))
    coke = rows[1]
    assert coke["put_call"] == "Put"


def test_parse_information_table_new_unit():
    xml_bytes = (FIXTURES / "info_table_new_unit.xml").read_bytes()
    rows = parse_information_table(xml_bytes, filed_at=date(2023, 2, 14))
    apple = rows[0]
    # 신규 단위 → 그대로 1,000,000,000
    assert apple["value_usd"] == 1_000_000_000

from datetime import date

from thirteen_f.core.dates import (
    quarter_end,
    quarter_start,
    quarter_label,
    parse_quarter,
    quarter_range,
)


def test_quarter_label_from_date():
    assert quarter_label(date(2024, 3, 15)) == "2024Q1"
    assert quarter_label(date(2024, 6, 30)) == "2024Q2"
    assert quarter_label(date(2024, 12, 1)) == "2024Q4"


def test_quarter_end_from_label():
    assert quarter_end("2024Q1") == date(2024, 3, 31)
    assert quarter_end("2024Q2") == date(2024, 6, 30)
    assert quarter_end("2024Q3") == date(2024, 9, 30)
    assert quarter_end("2024Q4") == date(2024, 12, 31)


def test_quarter_start_from_label():
    assert quarter_start("2024Q1") == date(2024, 1, 1)
    assert quarter_start("2024Q2") == date(2024, 4, 1)
    assert quarter_start("2024Q3") == date(2024, 7, 1)
    assert quarter_start("2024Q4") == date(2024, 10, 1)


def test_parse_quarter():
    assert parse_quarter("2024Q1") == (2024, 1)
    assert parse_quarter("2024q4") == (2024, 4)


def test_quarter_range_inclusive():
    rng = quarter_range("2023Q4", "2024Q2")
    assert rng == ["2023Q4", "2024Q1", "2024Q2"]

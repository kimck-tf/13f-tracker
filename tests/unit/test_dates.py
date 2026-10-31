from datetime import UTC, date, datetime

from thirteen_f.core.dates import (
    parse_quarter,
    quarter_end,
    quarter_label,
    quarter_range,
    quarter_start,
    sec_13f_deadline,
    sec_13f_due_at,
    us_federal_holidays,
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


def test_us_federal_holidays_2026_observed_dates():
    h = us_federal_holidays(2026)
    assert date(2026, 1, 19) in h  # MLK — 1월 3번째 월요일
    assert date(2026, 2, 16) in h  # Presidents' Day
    assert date(2026, 7, 3) in h  # 7/4이 토요일 → 금요일 관측
    assert date(2026, 11, 26) in h  # Thanksgiving — 11월 4번째 목요일
    assert date(2026, 12, 25) in h


def test_sec_13f_deadline_rolls_past_weekends_and_holidays():
    # 2/14 토 → 2/16 월은 Presidents' Day → 2/17 화
    assert sec_13f_deadline(date(2025, 12, 31)) == date(2026, 2, 17)
    # 11/14 토 → 11/16 월
    assert sec_13f_deadline(date(2026, 9, 30)) == date(2026, 11, 16)
    # 목요일 그대로
    assert sec_13f_deadline(date(2024, 9, 30)) == date(2024, 11, 14)
    # 금요일 그대로 — 그해 Presidents' Day는 2/17
    assert sec_13f_deadline(date(2024, 12, 31)) == date(2025, 2, 14)


def test_sec_13f_due_at_is_after_the_deadline_day_closes_in_new_york():
    # 기한일(11-16) 미 동부 17:30 뒤에 들어온 제출은 다음 날짜로 접수된다 — 22:30 UTC(한국 07:30)
    assert sec_13f_due_at(date(2026, 9, 30)) == datetime(2026, 11, 16, 22, 30, tzinfo=UTC)

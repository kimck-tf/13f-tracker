"""Quarter ↔ date 변환 유틸리티."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

_QUARTER_LAST_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}
_QUARTER_LAST_DAY = {1: 31, 2: 30, 3: 30, 4: 31}
_QUARTER_FIRST_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}


def quarter_label(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}Q{q}"


def parse_quarter(label: str) -> tuple[int, int]:
    label = label.upper()
    year_s, q_s = label.split("Q")
    year, q = int(year_s), int(q_s)
    if q not in (1, 2, 3, 4):
        raise ValueError(f"Invalid quarter: {label}")
    return year, q


def quarter_end(label: str) -> date:
    year, q = parse_quarter(label)
    return date(year, _QUARTER_LAST_MONTH[q], _QUARTER_LAST_DAY[q])


def quarter_start(label: str) -> date:
    year, q = parse_quarter(label)
    return date(year, _QUARTER_FIRST_MONTH[q], 1)


def quarter_range(start: str, end: str) -> list[str]:
    sy, sq = parse_quarter(start)
    ey, eq = parse_quarter(end)
    out: list[str] = []
    y, q = sy, sq
    while (y, q) <= (ey, eq):
        out.append(f"{y}Q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out



def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """그 달의 n번째 weekday(월요일 = 0)."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _observed(d: date) -> date:
    """토요일 공휴일은 금요일, 일요일 공휴일은 월요일에 쉰다."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def us_federal_holidays(year: int) -> set[date]:
    """그해 미국 연방 공휴일(현행 11개)의 관측일."""
    fixed = [(1, 1), (6, 19), (7, 4), (11, 11), (12, 25)]
    may_31 = date(year, 5, 31)
    return {_observed(date(year, m, d)) for m, d in fixed} | {
        _nth_weekday(year, 1, 0, 3),  # MLK
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        may_31 - timedelta(days=may_31.weekday()),  # Memorial Day — 5월 마지막 월요일
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 10, 0, 2),  # Columbus Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving — 11월 4번째 목요일
    }


def sec_13f_deadline(period_end: date) -> date:
    """13F 제출 기한: 분기말 + 45일, 토·일·연방 공휴일이면 다음 영업일 (Exchange Act Rule 0-3)."""
    deadline = period_end + timedelta(days=45)
    while deadline.weekday() >= 5 or deadline in us_federal_holidays(deadline.year):
        deadline += timedelta(days=1)
    return deadline



def sec_13f_due_at(period_end: date) -> datetime:
    """그 분기 13F를 모두 받을 수 있는 시각(UTC): 기한일 미 동부 17:30 — 그 뒤 제출은 다음 날짜로
    접수된다. EST·EDT를 따로 보지 않고 22:30 UTC(EST 17:30, EDT 18:30, 한국 다음 날 07:30)로
    둔다."""
    return datetime.combine(sec_13f_deadline(period_end), time(22, 30), tzinfo=UTC)

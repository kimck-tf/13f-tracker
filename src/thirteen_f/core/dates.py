"""Quarter ↔ date 변환 유틸리티."""
from __future__ import annotations

from datetime import date


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

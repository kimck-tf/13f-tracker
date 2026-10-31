from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.continuity import continuity_from_changes, update_continuity_scores


def test_full_buying_sequence():
    # [new, increase, hold, hold] (t-3→t) 모두 매집 → 4/4 = 1.0
    assert continuity_from_changes(["new", "increase", "hold", "hold"]) == 1.0


def test_break_resets():
    # [new, increase, decrease, hold] → decrease 이전 무시, 단 hold만 카운트 = 1/4 = 0.25
    assert continuity_from_changes(["new", "increase", "decrease", "hold"]) == pytest.approx(0.25)


def test_exit_breaks():
    # [hold, exit, new] → exit 이전 무시, new 1개만 카운트 = 1/4 = 0.25
    assert continuity_from_changes(["hold", "exit", "new"]) == pytest.approx(0.25)


def test_short_history():
    # 2분기만 있음 [new, increase] → 2/4 = 0.5
    assert continuity_from_changes(["new", "increase"]) == 0.5


def test_empty_history():
    assert continuity_from_changes([]) == 0.0


QS = [
    date(2023, 3, 31),
    date(2023, 6, 30),
    date(2023, 9, 30),
    date(2023, 12, 31),
    date(2024, 3, 31),
]


def test_sql_update_matches_reference_function(tmp_path):
    seqs = {
        "A": ["new", "increase", "decrease", "hold"],
        "B": ["hold", "exit", "new"],
        "C": ["new", "increase", "hold", "hold", "hold"],
    }
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    for cusip, seq in seqs.items():
        for i, ch in enumerate(seq):
            c.execute(
                "INSERT INTO signals_quarterly (cik, cusip, period_of_report, change_type) "
                "VALUES ('m', ?, ?, ?)",
                (cusip, QS[i], ch),
            )
    assert update_continuity_scores(c) == 12
    for cusip, seq in seqs.items():
        for i in range(len(seq)):
            got = c.execute(
                "SELECT continuity_score FROM signals_quarterly "
                "WHERE cusip = ? AND period_of_report = ?",
                (cusip, QS[i]),
            ).fetchone()[0]
            assert got == pytest.approx(continuity_from_changes(seq[: i + 1])), (cusip, i)
    c.close()

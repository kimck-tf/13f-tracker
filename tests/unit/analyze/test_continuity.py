import pytest

from thirteen_f.analyze.continuity import continuity_from_changes


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

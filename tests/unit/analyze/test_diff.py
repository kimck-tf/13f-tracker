import pytest

from thirteen_f.analyze.diff import classify_change


def test_new():
    assert classify_change(prev=None, curr=100, threshold=0.05) == "new"


def test_exit():
    assert classify_change(prev=100, curr=None, threshold=0.05) == "exit"


def test_hold_within_threshold():
    assert classify_change(prev=100, curr=104, threshold=0.05) == "hold"
    assert classify_change(prev=100, curr=96, threshold=0.05) == "hold"


def test_increase():
    assert classify_change(prev=100, curr=106, threshold=0.05) == "increase"
    assert classify_change(prev=100, curr=200, threshold=0.05) == "increase"


def test_decrease():
    assert classify_change(prev=100, curr=94, threshold=0.05) == "decrease"
    assert classify_change(prev=100, curr=10, threshold=0.05) == "decrease"


def test_prev_zero_treated_as_new():
    assert classify_change(prev=0, curr=100, threshold=0.05) == "new"

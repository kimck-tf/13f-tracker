import pytest

from thirteen_f.analyze.concentration import hhi


def test_hhi_equal_weights():
    # 4 종목 균등 (0.25 each) → 4 × 0.0625 = 0.25
    assert hhi([0.25, 0.25, 0.25, 0.25]) == pytest.approx(0.25)


def test_hhi_concentrated():
    # 1 종목 80% + 4 종목 5% = 0.64 + 4×0.0025 = 0.65
    assert hhi([0.80, 0.05, 0.05, 0.05, 0.05]) == pytest.approx(0.65)


def test_hhi_single_holding():
    assert hhi([1.0]) == 1.0


def test_hhi_empty():
    assert hhi([]) == 0.0

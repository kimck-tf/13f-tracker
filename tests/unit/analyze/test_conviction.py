import pytest

from thirteen_f.analyze.conviction import conviction_score


def test_conviction_top_weight_zero():
    assert conviction_score(weight_pct=0.05, top_weight=0.0, holding_count=5) == 0


def test_conviction_single_holding():
    # holding_count=1 → 1.0
    assert conviction_score(weight_pct=1.0, top_weight=1.0, holding_count=1) == 1.0


def test_conviction_normalize():
    assert conviction_score(weight_pct=0.05, top_weight=0.20, holding_count=10) == pytest.approx(0.25)
    assert conviction_score(weight_pct=0.20, top_weight=0.20, holding_count=10) == 1.0


def test_conviction_cap_at_one():
    # 안전망: weight_pct가 top_weight보다 큰 비정상은 cap
    assert conviction_score(weight_pct=0.30, top_weight=0.20, holding_count=10) == 1.0

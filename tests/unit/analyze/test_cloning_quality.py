import pytest

from thirteen_f.analyze.cloning_quality import cloning_quality_score


def test_cloning_simple_mean():
    # Spec §6.1: 단순 산술 평균 (가중 X)
    assert cloning_quality_score([1.0, 1.0, 0.5]) == pytest.approx(0.833, rel=1e-2)


def test_cloning_empty():
    assert cloning_quality_score([]) == 0.0


def test_cloning_single():
    assert cloning_quality_score([0.7]) == 0.7

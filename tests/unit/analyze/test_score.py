import pytest

from thirteen_f.analyze.score import (
    ScoreWeights,
    load_weights,
    weighted_total,
)


def test_load_weights_validates_sum(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        "[weights]\nconsensus=0.5\nconviction=0.5\ncontinuity=0.5\ncloning_quality=0.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="weights sum"):
        load_weights(bad)


def test_load_weights_ok(tmp_path):
    good = tmp_path / "good.toml"
    good.write_text(
        "[weights]\nconsensus=0.30\nconviction=0.30\ncontinuity=0.20\ncloning_quality=0.20\n",
        encoding="utf-8",
    )
    w = load_weights(good)
    assert w.consensus == 0.30
    assert w.conviction == 0.30
    assert w.continuity == 0.20
    assert w.cloning_quality == 0.20


def test_weighted_total():
    w = ScoreWeights(consensus=0.3, conviction=0.3, continuity=0.2, cloning_quality=0.2)
    total = weighted_total(
        consensus_s=1.0, conviction_s=0.5, continuity_s=0.0, cloning_quality_s=1.0, weights=w
    )
    # 1.0*0.3 + 0.5*0.3 + 0.0*0.2 + 1.0*0.2 = 0.3 + 0.15 + 0 + 0.2 = 0.65
    assert total == pytest.approx(0.65)

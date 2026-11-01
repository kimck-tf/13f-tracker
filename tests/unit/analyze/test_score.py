from datetime import date, timedelta

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.analyze.continuity import update_continuity_scores
from thirteen_f.analyze.conviction import update_conviction_scores
from thirteen_f.analyze.diff import compute_signals_quarterly
from thirteen_f.analyze.score import (
    ScoreWeights,
    compute_total_scores,
    load_weights,
    weighted_total,
)
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager


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


Q1, Q2 = date(2024, 3, 31), date(2024, 6, 30)


def _h(cusip, shares=10):
    return {
        "cusip": cusip,
        "name_of_issuer": cusip,
        "title_of_class": "COM",
        "value_usd": shares * 10,
        "shares": shares,
        "share_type": "SH",
        "put_call": "",
    }


def test_consensus_score_divides_by_that_quarters_filers(tmp_path):
    """Q1은 3명 제출·전원 AAA 보유, Q2는 2명만 제출 — 분모는 명단(3)이 아니라 제출자(2)."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    for cik in ("c1", "c2", "c3"):
        upsert_manager(
            c,
            {
                "cik": cik,
                "name": cik,
                "label": cik,
                "fund": "F",
                "style": "value",
                "active_since": 2020,
                "cloning_score_weight": 1.0,
            },
        )
    for acc, cik, p in [
        ("a1", "c1", Q1),
        ("a2", "c2", Q1),
        ("a3", "c3", Q1),
        ("b1", "c1", Q2),
        ("b2", "c2", Q2),
    ]:
        upsert_filing(
            c,
            {
                "accession_no": acc,
                "cik": cik,
                "form_type": "13F-HR",
                "period_of_report": p,
                "filed_at": p + timedelta(days=45),
                "is_amendment": False,
            },
        )
        upsert_holdings(c, acc, [_h("AAA")] + ([_h("BBB")] if acc == "b1" else []))
    compute_signals_quarterly(c)
    update_conviction_scores(c)
    update_continuity_scores(c)
    compute_consensus(c)
    compute_total_scores(
        c, ScoreWeights(consensus=0.3, conviction=0.3, continuity=0.2, cloning_quality=0.2)
    )
    score = {
        (p, cu): s
        for p, cu, s in c.execute(
            "SELECT period_of_report, cusip, consensus_score FROM total_scores"
        ).fetchall()
    }
    assert score[(Q1, "AAA")] == pytest.approx(1.0)
    assert score[(Q2, "AAA")] == pytest.approx(1.0)  # 2/2 — 종전 로직이면 2/3
    assert score[(Q2, "BBB")] == pytest.approx(0.5)
    c.close()

from thirteen_f.backtest.runner import default_suite


def test_default_suite_compares_buffett_and_druckenmiller_clones():
    names = [s.name for s in default_suite()]
    assert "SingleManagerClone(Buffett)" in names
    assert "SingleManagerClone(Druckenmiller)" in names
    # 전략 이름은 backtest_runs 저장·SPA 매칭 키라 중복되면 안 된다
    assert len(names) == len(set(names))


def test_default_suite_uses_sweep_optimized_params():
    """2026-09 파라미터 탐색(docs/backtest-optimization-2026-09.md)의 계열별 최적값.
    SPA Backtest 화면이 type당 최신 run 하나를 쓰므로 type당 1개만 둔다."""
    names = [s.name for s in default_suite()]
    assert names == [
        "SingleManagerClone(Buffett)",
        "SingleManagerClone(Druckenmiller)",
        "ConsensusTopK(3,10)",
        "ScoreTopK(40)",
        "ConvictionFollow(3)",
        "NewBuyOnly(2,15)",
        "Ensemble(ConsensusTopK(3,10):0.5,ConsensusTopK(2,15):0.5)",
        "MultiManager(4 mgrs, top=20)",
    ]
    multi = default_suite()[-1]
    assert multi.mgr_labels == ["Burry", "Dalio", "Druckenmiller", "Tepper"]

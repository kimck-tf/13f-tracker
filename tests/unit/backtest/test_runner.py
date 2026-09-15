from thirteen_f.backtest.runner import default_suite


def test_default_suite_compares_buffett_and_druckenmiller_clones():
    names = [s.name for s in default_suite()]
    assert "SingleManagerClone(Buffett)" in names
    assert "SingleManagerClone(Druckenmiller)" in names
    # 전략 이름은 backtest_runs 저장·SPA 매칭 키라 중복되면 안 된다
    assert len(names) == len(set(names))

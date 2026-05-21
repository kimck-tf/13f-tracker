import pytest

from thirteen_f.backtest.strategy import Strategy


def test_strategy_is_abstract():
    with pytest.raises(TypeError):
        Strategy()


def test_concrete_strategy_must_implement_get_target_positions():
    class Incomplete(Strategy):
        name = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()

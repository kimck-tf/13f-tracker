"""Backtest metrics. Spec §7.5."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def total_return(navs: Sequence[float]) -> float:
    if len(navs) < 2 or navs[0] == 0:
        return 0.0
    return navs[-1] / navs[0] - 1


def cagr(navs: Sequence[float], num_days: int) -> float:
    if len(navs) < 2 or navs[0] == 0:
        return 0.0
    growth = navs[-1] / navs[0]
    if growth <= 0:
        return -1.0
    years = num_days / 252.0
    if years <= 0:
        return 0.0
    return growth ** (1.0 / years) - 1


def sharpe(daily_returns: Sequence[float]) -> float:
    """무위험률 0 가정. Spec §7.5."""
    arr = np.asarray(daily_returns, dtype=float)
    if arr.size < 2:
        return 0.0
    sd = arr.std(ddof=0)
    if sd == 0:
        return float("inf") if arr.mean() > 0 else 0.0
    return float(arr.mean() / sd * math.sqrt(252))


def sortino(daily_returns: Sequence[float]) -> float:
    arr = np.asarray(daily_returns, dtype=float)
    if arr.size < 2:
        return 0.0
    downside = arr[arr < 0]
    if downside.size == 0:
        return float("inf") if arr.mean() > 0 else 0.0
    sd = downside.std(ddof=0)
    if sd == 0:
        return float("inf") if arr.mean() > 0 else 0.0
    return float(arr.mean() / sd * math.sqrt(252))


def max_drawdown(navs: Sequence[float]) -> float:
    if len(navs) < 2:
        return 0.0
    arr = np.asarray(navs, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (peak - arr) / peak
    return float(dd.max())


def calmar(cagr_value: float, mdd_value: float) -> float:
    if mdd_value == 0:
        return float("inf") if cagr_value > 0 else 0.0
    return cagr_value / mdd_value


def win_rate_quarterly(quarter_pnls: Sequence[float]) -> float:
    if not quarter_pnls:
        return 0.0
    wins = sum(1 for p in quarter_pnls if p > 0)
    return wins / len(quarter_pnls)

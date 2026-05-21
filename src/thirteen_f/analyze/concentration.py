"""Portfolio concentration metrics (HHI). Spec §6.3."""
from __future__ import annotations

from typing import Iterable


def hhi(weights: Iterable[float]) -> float:
    """Σ(w²). 0 = 완전 분산, 1 = 단일 종목."""
    return float(sum(w * w for w in weights))

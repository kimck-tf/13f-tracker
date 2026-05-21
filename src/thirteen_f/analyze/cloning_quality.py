"""Cloning quality score = simple arithmetic mean of holders' cloning_score_weight. Spec §6.1."""
from __future__ import annotations

from typing import Iterable


def cloning_quality_score(weights: Iterable[float]) -> float:
    weights = list(weights)
    if not weights:
        return 0.0
    return sum(weights) / len(weights)

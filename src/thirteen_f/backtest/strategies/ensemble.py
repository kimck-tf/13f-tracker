"""Ensemble: 여러 전략의 가중 평균."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class Ensemble(Strategy):
    def __init__(self, weights: dict[Strategy, float]) -> None:
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"Ensemble weights sum must be 1.0, got {total:.4f}"
            )
        self._weights = weights
        names = ",".join(f"{s.name}:{w}" for s, w in weights.items())
        self.name = f"Ensemble({names})"

    def params_json(self) -> str:
        return json.dumps(
            {s.name: w for s, w in self._weights.items()}
        )

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        combined: dict[str, float] = defaultdict(float)
        for sub, sub_w in self._weights.items():
            sub_targets = sub.get_target_positions(as_of_date, conn)
            for ticker, w in sub_targets.items():
                combined[ticker] += w * sub_w
        # 정규화 (sub가 빈 결과 반환했을 경우 합이 1.0보다 작을 수 있음)
        total = sum(combined.values())
        if total <= 0:
            return {}
        return {t: w / total for t, w in combined.items()}

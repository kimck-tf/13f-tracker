"""Strategy ABC. Spec §7.1."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import duckdb


class Strategy(ABC):
    name: str = "Strategy"

    @abstractmethod
    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        """Return target {ticker: weight}, weights sum to 1.0.

        Spec §7.1: Strategy가 weight 합 1.0 보장. ticker=null 종목은 Strategy 내부에서 제외.
        Spec §7.4: SQL은 filings.filed_at <= as_of_date 강제 (lookahead 차단).
        """
        ...

    def params_json(self) -> str:
        """직렬화. 기본은 클래스 이름만, 파라미터 있는 전략은 오버라이드."""
        import json
        return json.dumps({"name": self.name})


@dataclass
class BacktestResult:
    run_id: str
    strategy_name: str
    start_date: date
    end_date: date
    nav_series: list[tuple[date, float, float, int]]  # (date, nav, bench_nav, position_count)
    metrics: dict[str, float]
    params_json: str = ""
    benchmark: str = "SPY"
    cost_bps: float = 10.0

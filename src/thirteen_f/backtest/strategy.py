"""Strategy ABC. Spec §7.1."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

import duckdb

# 보통주가 아닌 클래스(워런트·권리)의 CUSIP. 13F titleOfClass는 SEC 공식 목록 표기(`*W EXP …`)를
# 따른다. 집계 전략이 발행사(CUSIP 앞 6자리)당 한 클래스를 고를 때 이런 클래스는 보통주 뒤로 미룬다.
NON_COMMON_CUSIPS_SQL = (
    "SELECT DISTINCT cusip FROM holdings WHERE title_of_class LIKE '*%' "
    "OR UPPER(title_of_class) LIKE '%WARRANT%' OR UPPER(title_of_class) LIKE '%RIGHT%'"
)


# 매니저별 최신 13F를 쓰는 전략(SingleManagerClone·ConvictionFollow·MultiManager)은 가장 최근에
# 제출된 분기보다 이만큼(분기 수) 이상 뒤처진 13F를 쓰지 않는다 — 13F를 그만 낸 매니저의 옛
# 포트폴리오가 계속 남지 않게 (Burry: 2025Q3이 마지막). 한 분기 차이는 제출 시차라 그대로 쓴다.
STALE_QUARTERS = 2


def fresh_period_sql(period_col: str) -> str:
    """``period_col`` 분기가 오래되지 않았다는 WHERE 조건. ``?`` 하나에 as_of_date를 넣는다."""
    return (
        f"date_diff('quarter', {period_col}, (SELECT MAX(period_of_report) FROM filings "
        f"WHERE form_type LIKE '13F-HR%' AND filed_at <= ?)) < {STALE_QUARTERS}"
    )


def latest_public_period(
    conn: duckdb.DuckDBPyConnection, as_of_date: date, table: str
) -> date | None:
    """as_of_date에 쓸 수 있는 ``table``(total_scores·consensus_quarterly)의 최신 분기.

    이 표들은 그 분기 매니저 전원의 보유를 합친 값이라, 첫 제출자가 아니라 **마지막 제출자의
    13F-HR 원본이 공개된 뒤**(Spec §7.4 lookahead 차단)에야 분기를 쓸 수 있다. 정정본(13F-HR/A)은
    원본이 이미 공개된 뒤의 소폭 수정이라 기준일에 넣지 않는다.
    """
    row = conn.execute(
        f"""
        SELECT MAX(t.period_of_report)
        FROM {table} t
        WHERE t.period_of_report IN (
            SELECT period_of_report FROM filings
            WHERE form_type = '13F-HR'
            GROUP BY period_of_report
            HAVING MAX(filed_at) <= ?
        )
        """,
        (as_of_date,),
    ).fetchone()
    return row[0] if row else None


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
    # quarter_label -> (rebalance_date, {ticker: weight}) — Phase 5 A4: backtest_holdings persist
    holdings_log: dict[str, tuple[date, dict[str, float]]] = field(default_factory=dict)

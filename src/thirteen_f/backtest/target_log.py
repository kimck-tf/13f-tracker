"""target_log — 그때그때 지시한 목표 비중을 쌓기만 하는 기록.

analyze는 지난 분기의 점수까지 매번 다시 계산하므로, 규칙이나 데이터가 바뀌면 지나간 분기의
목표도 함께 바뀐다. 백테스트는 늘 지금의 규칙으로 과거를 다시 그리기 때문에, 그때 실제로
무엇을 지시했는지는 따로 적어 두지 않으면 남지 않는다. 이 기록이 쌓여야 규칙을 고르는 데 쓰지
않은 자료로 전략을 검증할 수 있다.
"""
from __future__ import annotations

import json
from datetime import date, datetime

import duckdb

from thirteen_f.backtest.engine import tradeable_at
from thirteen_f.backtest.runner import default_suite
from thirteen_f.backtest.strategy import latest_public_period


def record_targets(conn: duckdb.DuckDBPyConnection, as_of: date) -> list[str]:
    """기본 suite 전략의 ``as_of`` 기준 목표 비중을 target_log에 쌓는다.

    새로 적은 전략 이름을 돌려준다. 목표는 Plan 탭과 같다 — ``get_target_positions`` 뒤 가격이
    끊긴 종목을 뺀 것(``tradeable_at``). 전략마다 직전 기록과 목표·파라미터가 같으면 건너뛰고,
    다르면(첫 기록 포함) 한 줄을 더한다. 있던 줄은 고치지도 지우지도 않는다. 목표가 없으면(현금)
    ``{}``로 적는다. ``period_of_report``는 그때 매니저 전원의 13F가 공개돼 있던 최신 분기다.
    파라미터(``params_json``)를 함께 적는 것은 이름이 전략을 다 가리지 못해서다 — MultiManager의
    이름에는 매니저 수만 들어간다. 이 칸이 생기기 전의 줄(NULL)과는 목표만 견준다.
    """
    period = latest_public_period(conn, as_of, "total_scores")
    now = datetime.now()
    recorded: list[str] = []
    for strat in default_suite():
        target = tradeable_at(conn, strat.get_target_positions(as_of_date=as_of, conn=conn), as_of)
        payload = json.dumps({t: round(w, 6) for t, w in sorted(target.items())})
        params = strat.params_json()
        last = conn.execute(
            "SELECT targets_json, params_json FROM target_log WHERE strategy_name = ? "
            "ORDER BY recorded_at DESC LIMIT 1",
            (strat.name,),
        ).fetchone()
        if last and last[0] == payload and last[1] in (None, params):
            continue
        conn.execute(
            "INSERT INTO target_log (strategy_name, recorded_at, as_of, period_of_report, "
            "targets_json, params_json) VALUES (?, ?, ?, ?, ?, ?)",
            (strat.name, now, as_of, period, payload, params),
        )
        recorded.append(strat.name)
    return recorded

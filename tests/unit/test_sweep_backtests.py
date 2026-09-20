import csv
from datetime import date, timedelta

import duckdb
import pytest

from scripts.init_db import init_db
from scripts.sweep_backtests import build_configs, run_sweep, window_metrics


def test_build_configs_only_matches_family_or_config_label():
    """--only는 계열 이름뿐 아니라 설정 라벨(mh3_top10, e2_…)에도 부분 일치한다 — 2차 탐색에서
    새로 넣은 앙상블만 골라 돌리기 위해."""
    assert [c[0] for c in build_configs(only="ConsensusTopK")] == ["ConsensusTopK"] * 15
    assert [(c[0], c[1]) for c in build_configs(only="value6_top30")] == [
        ("MultiManager", "value6_top30")
    ]


def _series(values, bench, positions):
    return [
        (date(2024, 1, 1 + i), v, b, p)
        for i, (v, b, p) in enumerate(zip(values, bench, positions, strict=True))
    ]


def test_window_metrics_uses_only_rows_inside_the_window():
    """전·후반 분할 지표는 같은 일별 NAV에서 구간만 잘라 계산한다 (재실행 없이)."""
    series = _series(
        values=[100, 110, 99, 120, 130],
        bench=[100, 101, 102, 103, 104],
        positions=[0, 2, 2, 3, 3],
    )
    m = window_metrics(series, start=date(2024, 1, 2), end=date(2024, 1, 4))
    # 110 → 120: 총수익 +9.09%, 최대 낙폭 110 → 99 = 10%
    assert m["total_return"] == pytest.approx(120 / 110 - 1)
    assert m["mdd"] == pytest.approx(0.1)
    assert m["bench_total_return"] == pytest.approx(103 / 101 - 1)
    assert m["alpha_cagr"] == pytest.approx(m["cagr"] - m["bench_cagr"])
    assert m["days"] == 3


def test_window_metrics_reports_average_positions_over_invested_days():
    series = _series(
        values=[100, 100, 105, 110],
        bench=[100, 100, 100, 100],
        positions=[0, 0, 4, 6],
    )
    m = window_metrics(series, start=date(2024, 1, 1), end=date(2024, 1, 4))
    # 현금인 날(0종목)은 평균에서 빼고, 투자한 날 비율은 따로 센다
    assert m["avg_positions"] == pytest.approx(5.0)
    assert m["min_positions"] == 4
    assert m["invested_frac"] == pytest.approx(0.5)


def test_window_metrics_empty_window_returns_zero_days():
    series = _series(values=[100, 101], bench=[100, 100], positions=[1, 1])
    m = window_metrics(series, start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert m["days"] == 0
    assert m["cagr"] == 0.0 and m["mdd"] == 0.0


def test_run_sweep_append_keeps_previous_rows_and_db(tmp_path):
    """2차 탐색(--append)은 1차 CSV 뒤에 행을 붙이고 사본 DB의 run도 지우지 않는다."""
    src = tmp_path / "src.duckdb"
    init_db(src)
    c = duckdb.connect(str(src))
    for i in range(5):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, NULL, NULL, NULL, 100, 100, 0)",
                  (date(2024, 5, 13) + timedelta(days=i),))
    c.close()
    out = tmp_path / "sweep"
    args = dict(start=date(2024, 5, 13), end=date(2024, 5, 17), split=date(2024, 5, 15),
                cost_bps=10.0, only="default")  # 현행 default_suite의 Ensemble 1개

    csv_path = run_sweep(src, out, **args)
    run_sweep(src, out, **args, append=True)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert [r["family"] for r in rows] == ["Ensemble", "Ensemble"]
    c = duckdb.connect(str(out / "13f.sweep.duckdb"), read_only=True)
    assert c.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0] == 2
    c.close()

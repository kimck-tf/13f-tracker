"""백테스트 파라미터 탐색 — DB 사본에서 전략 설정 수십 개를 돌려 CSV로 비교.

uv run python scripts/sweep_backtests.py                          # data/13f.duckdb → data/sweep/
uv run python scripts/sweep_backtests.py --only ConsensusTopK     # 한 계열만
uv run python scripts/sweep_backtests.py --only Ensemble --append # 2차: 이전 결과 뒤에 붙임
uv run python scripts/sweep_backtests.py --start 2024-05-13 --end 2026-09-14 --split 2025-08-14

본 DB(data/13f.duckdb)와 SPA용 JSON은 건드리지 않는다. run은 사본(data/sweep/13f.sweep.duckdb)에
persist하므로 곡선·보유 내역은 그 DB에서 다시 볼 수 있다. 전·후반 지표는 같은 일별 NAV를
--split 기준으로 잘라 계산한다(재실행 없음). 설정당 약 9초.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

from thirteen_f.backtest.engine import run_backtest
from thirteen_f.backtest.metrics import cagr, calmar, max_drawdown, sharpe, total_return
from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
from thirteen_f.backtest.strategies.conviction_follow import ConvictionFollow
from thirteen_f.backtest.strategies.ensemble import Ensemble
from thirteen_f.backtest.strategies.multi_manager import MultiManager
from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
from thirteen_f.backtest.strategies.score_top_k import ScoreTopK
from thirteen_f.backtest.strategies.single_manager import SingleManagerClone
from thirteen_f.backtest.strategy import Strategy

ALL_MANAGERS = [
    "Ackman", "Akre", "Buffett", "Burry", "Dalio", "Druckenmiller", "Einhorn",
    "Icahn", "Klarman", "LiLu", "Loeb", "Nygren", "Pabrai", "Tepper",
]
MANAGER_SETS = {
    "current3": ["Buffett", "Ackman", "Tepper"],
    "value6": ["Akre", "Buffett", "Klarman", "LiLu", "Nygren", "Pabrai"],
    "activist4": ["Ackman", "Einhorn", "Icahn", "Loeb"],
    "macro4": ["Burry", "Dalio", "Druckenmiller", "Tepper"],
    "all14": ALL_MANAGERS,
}
# 2차 탐색(e2_*): 1차 결과의 1위 ConsensusTopK(3,10)을 핵심으로 두고, 성격이 다른 상위 설정을 섞어
# MDD가 줄어드는지 본다. "default"는 현행 default_suite의 Ensemble.
ENSEMBLES: dict[str, dict[Strategy, float]] = {
    "default": {
        SingleManagerClone(label="Buffett"): 0.4,
        ScoreTopK(top_k=20): 0.4,
        ConsensusTopK(min_holders=3, top_k=20): 0.2,
    },
    "e2_cons_macro": {
        ConsensusTopK(min_holders=3, top_k=10): 0.6,
        MultiManager(mgr_labels=MANAGER_SETS["macro4"], top_k=20): 0.4,
    },
    "e2_cons_druck": {
        ConsensusTopK(min_holders=3, top_k=10): 0.6,
        SingleManagerClone(label="Druckenmiller"): 0.4,
    },
    "e2_cons_conviction": {
        ConsensusTopK(min_holders=3, top_k=10): 0.5,
        ConvictionFollow(top_k=3): 0.5,
    },
    "e2_cons_value": {
        ConsensusTopK(min_holders=3, top_k=10): 0.6,
        MultiManager(mgr_labels=MANAGER_SETS["value6"], top_k=30): 0.4,
    },
    "e2_cons_cons": {
        ConsensusTopK(min_holders=3, top_k=10): 0.5,
        ConsensusTopK(min_holders=2, top_k=15): 0.5,
    },
    "e2_top3_equal": {
        ConsensusTopK(min_holders=3, top_k=10): 0.34,
        MultiManager(mgr_labels=MANAGER_SETS["macro4"], top_k=20): 0.33,
        ConvictionFollow(top_k=3): 0.33,
    },
}

WINDOW_KEYS = [
    "days", "total_return", "cagr", "mdd", "sharpe", "calmar", "bench_total_return",
    "bench_cagr", "alpha_cagr", "avg_positions", "min_positions", "invested_frac",
]


def window_metrics(
    nav_series: list[tuple[date, float, float, int]], start: date, end: date
) -> dict[str, float]:
    """일별 NAV 시리즈에서 [start, end] 구간만 잘라 수익률·MDD 등을 계산한다."""
    rows = [r for r in nav_series if start <= r[0] <= end]
    if not rows:
        return {k: 0.0 for k in WINDOW_KEYS} | {"days": 0, "min_positions": 0}
    navs = [r[1] for r in rows]
    bench = [r[2] for r in rows]
    daily = [navs[i] / navs[i - 1] - 1 for i in range(1, len(navs)) if navs[i - 1] > 0]
    c = cagr(navs, num_days=len(navs))
    m = max_drawdown(navs)
    bench_c = cagr(bench, num_days=len(bench))
    invested = [r[3] for r in rows if r[3] > 0]
    return {
        "days": len(rows),
        "total_return": total_return(navs),
        "cagr": c,
        "mdd": m,
        "sharpe": sharpe(daily),
        "calmar": calmar(c, m),
        "bench_total_return": total_return(bench),
        "bench_cagr": bench_c,
        "alpha_cagr": c - bench_c,
        "avg_positions": sum(invested) / len(invested) if invested else 0.0,
        "min_positions": min(invested) if invested else 0,
        "invested_frac": len(invested) / len(rows),
    }


def build_configs(only: str | None = None) -> list[tuple[str, str, Strategy]]:
    """(계열, 설정 라벨, 전략) 목록. only가 있으면 계열 이름이나 설정 라벨에 그 문자열이 든 것만."""
    configs: list[tuple[str, str, Strategy]] = []
    for k in (5, 10, 15, 20, 30, 40):
        configs.append(("ScoreTopK", f"top{k}", ScoreTopK(top_k=k)))
    for mh in (2, 3, 4):
        for k in (5, 10, 15, 20, 30):
            configs.append(("ConsensusTopK", f"mh{mh}_top{k}", ConsensusTopK(mh, k)))
    for mh in (2, 3):
        for k in (5, 10, 15):
            for mp in (1, 5):
                configs.append((
                    "NewBuyOnly", f"mh{mh}_top{k}_min{mp}",
                    NewBuyOnly(min_holders=mh, top_k=k, min_positions=mp),
                ))
    for k in (3, 5, 10, 15, 20):
        configs.append(("ConvictionFollow", f"top{k}", ConvictionFollow(top_k=k)))
    for set_name, labels in MANAGER_SETS.items():
        for k in (10, 15, 20, 30):
            configs.append((
                "MultiManager", f"{set_name}_top{k}", MultiManager(mgr_labels=labels, top_k=k),
            ))
    for label in ALL_MANAGERS:
        configs.append(("SingleManagerClone", label, SingleManagerClone(label=label)))
    for name, weights in ENSEMBLES.items():
        configs.append(("Ensemble", name, Ensemble(weights=weights)))
    if only:
        needle = only.lower()
        configs = [c for c in configs if needle in c[0].lower() or needle in c[1].lower()]
    return configs


def run_sweep(
    src_db: Path, out_dir: Path, start: date, end: date, split: date,
    cost_bps: float, only: str | None, append: bool = False,
) -> Path:
    """append=True면 이전 탐색의 사본 DB와 CSV를 지우지 않고 뒤에 붙인다 (2차 탐색용)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sweep_db = out_dir / "13f.sweep.duckdb"
    csv_path = out_dir / "sweep_results.csv"
    append = append and sweep_db.exists() and csv_path.exists()
    if not append:
        shutil.copyfile(src_db, sweep_db)  # 새 사본 — 이전 탐색 run이 누적되지 않게
    configs = build_configs(only)
    fields = ["family", "config", "name", "params", "run_id", "seconds"] + [
        f"{w}_{k}" for w in ("full", "h1", "h2") for k in WINDOW_KEYS
    ]
    conn = duckdb.connect(str(sweep_db))
    try:
        with csv_path.open("a" if append else "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if not append:
                writer.writeheader()
            for i, (family, config, strat) in enumerate(configs, 1):
                t0 = time.perf_counter()
                res = run_backtest(strat, start, end, conn, cost_bps=cost_bps, persist=True)
                secs = time.perf_counter() - t0
                row: dict[str, object] = {
                    "family": family, "config": config, "name": res.strategy_name,
                    "params": res.params_json, "run_id": res.run_id, "seconds": round(secs, 1),
                }
                windows = {
                    "full": window_metrics(res.nav_series, start, end),
                    "h1": window_metrics(res.nav_series, start, split),
                    "h2": window_metrics(res.nav_series, split + timedelta(days=1), end),
                }
                for w, m in windows.items():
                    row.update({f"{w}_{k}": m[k] for k in WINDOW_KEYS})
                writer.writerow(row)
                f.flush()
                full = windows["full"]
                print(
                    f"[{i:3d}/{len(configs)}] {family:18s} {config:22s} "
                    f"CAGR={full['cagr']*100:6.2f}% MDD={full['mdd']*100:6.2f}% "
                    f"Calmar={full['calmar']:5.2f} pos={full['avg_positions']:5.1f} "
                    f"({secs:.0f}s)", flush=True,
                )
    finally:
        conn.close()
    return csv_path


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--db", type=Path, default=Path("data/13f.duckdb"))
    p.add_argument("--out", type=Path, default=Path("data/sweep"))
    p.add_argument("--start", default="2024-05-13", help="첫 13F 공개일 (그 전엔 모두 현금)")
    p.add_argument("--end", default="2026-09-14")
    p.add_argument("--split", default="2025-08-14", help="전·후반 분할일 (전반 = start~split)")
    p.add_argument("--cost-bps", type=float, default=10.0)
    p.add_argument("--only", default=None, help="계열 이름 부분 일치 (예: ConsensusTopK)")
    p.add_argument("--append", action="store_true", help="이전 결과 뒤에 붙임 (사본 DB·CSV 유지)")
    a = p.parse_args()
    d = lambda s: datetime.fromisoformat(s).date()  # noqa: E731
    csv_path = run_sweep(
        a.db, a.out, d(a.start), d(a.end), d(a.split), a.cost_bps, a.only, append=a.append
    )
    print(f"\nresults: {csv_path}")


if __name__ == "__main__":
    main()

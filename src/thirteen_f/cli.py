"""thirteen-f CLI 진입점 (typer)."""
from __future__ import annotations

import typer

app = typer.Typer(no_args_is_help=True, help="13F portfolio tracker CLI")


@app.command()
def collect(
    start: str = typer.Option("2011Q1", help="시작 분기 (예: 2011Q1)"),
) -> None:
    """Phase 1: EDGAR 수집 + 가격 다운로드."""
    from pathlib import Path

    from thirteen_f.collect.pipeline import run_collect
    from thirteen_f.core.config import load_settings
    from thirteen_f.core.dates import quarter_start
    from thirteen_f.core.logging import get_logger

    settings = load_settings()
    log = get_logger(log_dir=Path("data/logs"))
    log.info("Phase 1 collect start (start=%s)", start)
    stats = run_collect(
        settings=settings,
        managers_yaml=Path("config/managers.yaml"),
        db_path=settings.duckdb_path,
        start_date=quarter_start(start),
        failure_log=Path("data/logs/failed_tickers.jsonl"),
    )
    log.info("collect done: %s", stats)
    typer.echo(f"OK: {stats}")


@app.command()
def analyze(
    threshold: float = typer.Option(0.05, help="hold/increase/decrease 분류 threshold"),
) -> None:
    """Phase 2: 시그널 점수 계산."""
    from pathlib import Path

    from thirteen_f.analyze.pipeline import run_analyze
    from thirteen_f.core.config import load_settings
    from thirteen_f.core.logging import get_logger

    settings = load_settings()
    log = get_logger(log_dir=Path("data/logs"))
    log.info("Phase 2 analyze start (threshold=%.3f)", threshold)
    stats = run_analyze(
        db_path=settings.duckdb_path,
        scoring_toml=Path("config/scoring.toml"),
        diff_threshold=threshold,
    )
    log.info("analyze done: %s", stats)
    typer.echo(f"OK: {stats}")


@app.command()
def backtest(
    strategy: str = typer.Option(None, help="실행할 전략 이름. --all과 동시 사용 금지."),
    all_: bool = typer.Option(False, "--all", help="등록된 6개 전략 모두 실행."),
    start: str = typer.Option("2013-01-01", help="백테스트 시작일 (YYYY-MM-DD)"),
    end: str = typer.Option(None, help="백테스트 종료일 (YYYY-MM-DD, 기본=오늘)"),
    cost_bps: float = typer.Option(10.0, help="편도 거래비용 (bp)"),
) -> None:
    """Phase 3: 백테스트 실행. --all 또는 --strategy 중 하나 지정."""
    from datetime import date as _date, datetime
    from pathlib import Path

    from thirteen_f.backtest.runner import run_suite
    from thirteen_f.core.config import load_settings
    from thirteen_f.core.logging import get_logger

    if not all_ and not strategy:
        typer.echo("Either --all or --strategy must be set", err=True)
        raise typer.Exit(1)

    settings = load_settings()
    get_logger(log_dir=Path("data/logs"))
    s = datetime.fromisoformat(start).date()
    e = datetime.fromisoformat(end).date() if end else _date.today()

    if all_:
        results = run_suite(settings.duckdb_path, s, e, cost_bps=cost_bps)
        for r in results:
            typer.echo(
                f"{r['name']:60s} CAGR={r['cagr']*100:6.2f}%  "
                f"MDD={r['mdd']*100:6.2f}%  Sharpe={r['sharpe']:.2f}"
            )
        return

    # 단일 전략 실행 (간단한 dispatch)
    import duckdb

    from thirteen_f.backtest.engine import run_backtest
    from thirteen_f.backtest.strategies.consensus_top_k import ConsensusTopK
    from thirteen_f.backtest.strategies.conviction_follow import ConvictionFollow
    from thirteen_f.backtest.strategies.new_buy_only import NewBuyOnly
    from thirteen_f.backtest.strategies.score_top_k import ScoreTopK
    from thirteen_f.backtest.strategies.single_manager import SingleManagerClone

    registry = {
        "ScoreTopK": lambda: ScoreTopK(top_k=20),
        "ConsensusTopK": lambda: ConsensusTopK(min_holders=3, top_k=20),
        "ConvictionFollow": lambda: ConvictionFollow(top_k=10),
        "NewBuyOnly": lambda: NewBuyOnly(min_holders=2, top_k=15),
    }
    if strategy.startswith("SingleManagerClone("):
        label = strategy.split("(")[1].rstrip(")")
        strat = SingleManagerClone(label=label)
    elif strategy in registry:
        strat = registry[strategy]()
    else:
        typer.echo(f"Unknown strategy: {strategy}", err=True)
        raise typer.Exit(1)

    conn = duckdb.connect(str(settings.duckdb_path))
    try:
        res = run_backtest(
            strategy=strat, start=s, end=e, conn=conn,
            cost_bps=cost_bps, persist=True,
        )
        typer.echo(f"{strat.name}: {res.metrics}")
    finally:
        conn.close()


@app.command()
def dashboard() -> None:
    """Phase 4: Streamlit 대시보드 실행."""
    import subprocess
    from pathlib import Path

    app_path = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run(["streamlit", "run", str(app_path)], check=False)


@app.command()
def report(
    quarter: str = typer.Option(None, help="분기 라벨 (예: 2026Q1)"),
    latest: bool = typer.Option(False, "--latest", help="DB 최신 분기 자동 선택"),
    open_: bool = typer.Option(False, "--open", help="렌더 후 브라우저 열기"),
) -> None:
    """Phase 4: Quarto 분기 리포트 생성."""
    import os as _os
    import shutil
    import subprocess
    import webbrowser
    from pathlib import Path

    if shutil.which("quarto") is None:
        typer.echo(
            "Quarto CLI 미설치. Windows: winget install RStudio.Quarto", err=True
        )
        raise typer.Exit(2)

    if not quarter and not latest:
        typer.echo("Either --quarter or --latest must be set", err=True)
        raise typer.Exit(1)

    q_arg = "latest" if latest else quarter
    out_dir = Path("reports/output") / (q_arg if q_arg != "latest" else "_latest")
    cmd = [
        "quarto", "render", "reports/quarto/",
        "--output-dir", str(out_dir.absolute()),
    ]
    # Spec §8.2: quarter는 환경변수로 전달 (Quarto -P shortcode 호환성 문제 회피)
    # quarto가 cwd를 reports/quarto/ 로 바꿔 .env를 못 찾고, 상대경로(DUCKDB_PATH 등)도
    # 잘못 해석되는 문제를 둘 다 해결 — .env 명시 로드 + 경로 절대화 후 env 주입
    from dotenv import dotenv_values
    env = _os.environ.copy()
    env_file_vars = dotenv_values(Path(".env"))
    env.update({k: v for k, v in env_file_vars.items() if v is not None})
    db_path = env_file_vars.get("DUCKDB_PATH", "data/13f.duckdb")
    if db_path is not None:
        env["DUCKDB_PATH"] = str(Path(db_path.strip('"')).resolve())
    env["THIRTEEN_F_QUARTER"] = q_arg
    typer.echo(f"Running: {' '.join(cmd)} (THIRTEEN_F_QUARTER={q_arg})")
    result = subprocess.run(cmd, check=False, env=env)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)

    index_html = out_dir / "index.html"
    typer.echo(f"Output: {index_html}")
    if open_ and index_html.exists():
        webbrowser.open(str(index_html.absolute()))


@app.command()
def export(
    out: str = typer.Option(
        "",
        help="Output directory for JSON files (default: src/thirteen_f/web/data)",
    ),
) -> None:
    """Phase 5: DuckDB → JSON dump for the static SPA."""
    from pathlib import Path

    from thirteen_f.core.config import load_settings
    from thirteen_f.web.cli import do_export

    settings = load_settings()
    out_path = Path(out) if out else Path("src/thirteen_f/web/data")
    do_export(
        out=out_path,
        llm_available=bool(settings.google_api_key),
        db_path=str(settings.duckdb_path),
    )


@app.command()
def update(
    skip_collect: bool = typer.Option(False, help="collect 단계 건너뛰기"),
    skip_backtest: bool = typer.Option(False, help="backtest 단계 건너뛰기"),
    skip_export: bool = typer.Option(False, help="export 단계 건너뛰기 (Phase 5)"),
    skip_report: bool = typer.Option(False, help="report 단계 건너뛰기"),
) -> None:
    """collect → analyze → backtest --all → export → report --latest 순차 실행.

    ⚠️ typer command 함수를 Python에서 직접 호출하면 OptionInfo 기본값이 그대로
    전달되어 타입 에러 발생. 따라서 subprocess로 자기 자신(thirteen-f CLI)을
    재호출. 분기 1회 사용이라 overhead 무시 가능.
    """
    import subprocess
    import sys

    def run_step(args: list[str]) -> None:
        cmd = [sys.executable, "-m", "thirteen_f.cli", *args]
        typer.echo(f"$ {' '.join(cmd[2:])}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            typer.echo(f"step failed: {args[0]} (exit={result.returncode})", err=True)
            raise typer.Exit(result.returncode)

    if not skip_collect:
        typer.echo("=== Phase 1: collect ===")
        run_step(["collect"])
    typer.echo("=== Phase 2: analyze ===")
    run_step(["analyze"])
    if not skip_backtest:
        typer.echo("=== Phase 3: backtest --all ===")
        run_step(["backtest", "--all"])
    if not skip_export:
        typer.echo("=== Phase 5: export (DuckDB -> JSON for SPA) ===")
        run_step(["export"])
    if not skip_report:
        typer.echo("=== Phase 4: report --latest ===")
        run_step(["report", "--latest"])
    typer.echo("=== Update complete ===")


if __name__ == "__main__":
    app()

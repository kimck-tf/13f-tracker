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
def analyze() -> None:
    """Phase 2: 시그널 점수 계산."""
    typer.echo("analyze: not implemented yet (Phase 2)")


@app.command()
def backtest(
    strategy: str = typer.Option(None, help="실행할 전략 이름. --all과 동시 사용 금지."),
    all_: bool = typer.Option(False, "--all", help="등록된 6개 전략 모두 실행."),
) -> None:
    """Phase 3: 백테스트 실행."""
    typer.echo(f"backtest: not implemented yet (Phase 3). args={strategy=} {all_=}")


@app.command()
def dashboard() -> None:
    """Phase 4: Streamlit 대시보드."""
    typer.echo("dashboard: not implemented yet (Phase 4)")


@app.command()
def report(
    quarter: str = typer.Option(None, help="분기 라벨 (예: 2026Q1)"),
    latest: bool = typer.Option(False, "--latest", help="DB 최신 분기 자동 선택"),
    open_: bool = typer.Option(False, "--open", help="렌더 후 브라우저 열기"),
) -> None:
    """Phase 4: Quarto 분기 리포트 생성."""
    typer.echo(f"report: not implemented yet. args={quarter=} {latest=} {open_=}")


@app.command()
def update() -> None:
    """collect → analyze → backtest --all → report --latest 순차 실행."""
    typer.echo("update: not implemented yet")


if __name__ == "__main__":
    app()

# 13F Portfolio Tracker

미국 투자 거장 15명의 13F 공시 데이터를 EDGAR에서 직접 수집·분석·백테스트하는 개인용 도구.

## Setup

```bash
uv venv
uv sync
cp .env.example .env  # SEC_USER_AGENT 입력
uv run python scripts/init_db.py
```

## Quick Start

```bash
uv run thirteen-f collect
uv run thirteen-f analyze
uv run thirteen-f backtest --all
uv run thirteen-f dashboard
uv run thirteen-f report --latest --open
```

자세한 설계는 `docs/superpowers/specs/` 참조.

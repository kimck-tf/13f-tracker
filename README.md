# 13F Portfolio Tracker

미국 투자 거장 15명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## What it does

- **수집**: SEC EDGAR에서 분기별 13F-HR 공시 직접 파싱 (httpx + lxml)
- **분석**: 분기 간 변화·conviction·continuity·consensus 4 시그널 + 가중 종합 점수
- **시각화** (예정): Streamlit 대시보드 + Quarto 분기 리포트
- **백테스트** (예정): 6 전략 (SingleManagerClone, ConsensusTopK, ScoreTopK 등) + Lookahead-free 검증

## Tracked Managers (15)

| 스타일 | 거장 |
|---|---|
| Value / Quality (7) | Buffett, Klarman, Akre, Li Lu, Pabrai, Greenblatt, Nygren |
| Activist (4) | Ackman, Loeb, Einhorn, Icahn |
| Macro / Contrarian (4) | Tepper, Druckenmiller, Burry, Dalio |

## Setup

```bash
# 1) Python 환경 (uv 필요)
uv venv
uv sync

# 2) .env (SEC fair-access policy)
cp .env.example .env
# .env 편집 → SEC_USER_AGENT="Your Name email@domain.com"

# 3) DuckDB 11 테이블 초기화
uv run python scripts/init_db.py
```

## Quick Start

```bash
# Phase 1: EDGAR 분기 수집 (~25분, OpenFIGI + yfinance)
uv run thirteen-f collect --start 2024Q1

# Phase 2: 시그널 + 종합 점수
uv run thirteen-f analyze

# Top 20 시그널 (최신 분기)
uv run python -c "
import duckdb
c = duckdb.connect('data/13f.duckdb', read_only=True)
print(c.execute('''
    SELECT t.period_of_report, t.ticker, ROUND(t.total_score,3) AS score,
           cq.holder_count, cq.new_buy_count
    FROM total_scores t
    JOIN consensus_quarterly cq USING (period_of_report, cusip)
    WHERE t.period_of_report = (SELECT MAX(period_of_report) FROM total_scores)
    ORDER BY t.total_score DESC LIMIT 20
''').fetchdf().to_string(index=False))
"
```

## Progress Status

- [x] Phase 0 — 환경 셋업, DuckDB 11 테이블, CLI scaffolding
- [x] Phase 1 — EDGAR 수집 (15명 / 110 filings / 10,867 holdings / 1,584 price tickers)
- [x] Phase 2 — 4 시그널 + 종합 점수 (10,759 signals / 8,785 total_scores)
- [x] Phase 3 — Strategy ABC + 6 전략 + Lookahead 가드 + Engine + Runner
- [ ] Phase 4 — Streamlit 대시보드 + Quarto 분기 리포트

104 unit tests passed.

## CLI Commands

| Command | Phase | Status |
|---|---|---|
| `thirteen-f collect [--start QUARTER]` | 1 | done |
| `thirteen-f analyze [--threshold FLOAT]` | 2 | done |
| `thirteen-f backtest [--strategy NAME / --all] [--start --end --cost-bps]` | 3 | done |
| `thirteen-f dashboard` | 4 | todo |
| `thirteen-f report [--quarter Q / --latest] [--open]` | 4 | todo |
| `thirteen-f update` | all | todo |

## Tech Stack

Python ≥ 3.11 / uv / httpx / lxml / duckdb / polars / pyyaml / typer / yfinance / rich / tenacity / streamlit + plotly + Quarto (Phase 4)

## Design References

- 디자인 스펙: `docs/superpowers/specs/2026-05-20-13f-tracker-design.md`
- 구현 계획: `docs/superpowers/plans/2026-05-21-13f-tracker.md`
- 사전 조사: `참고/` (PLAN.md, edgar_notes.md, schema.md)
- 프로젝트 가이드: `CLAUDE.md`

## 13F Data Limitations

1. **45일 지연** — 공개 시점엔 포지션이 변경되어 있을 수 있음
2. **롱 온리** — 숏/헤지/장외 파생 미공개
3. **미국 상장 주식만** — 해외주·채권·현금·사모 제외
4. **분기 스냅샷** — 분기 중간 매매는 보이지 않음
5. **Confidential Treatment** — 일부 거장은 보유 종목을 일정 기간 비공개 유지 가능 (Buffett 사례 다수)

이는 13F 데이터의 본질적 한계이며 백테스트 해석 시 반드시 고려해야 합니다.

## License

Personal use.

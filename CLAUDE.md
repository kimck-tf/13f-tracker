# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 13F Portfolio Tracker — Project Guide

미국 투자 거장 15명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## Status (as of 2026-05-22)

- [x] **Phase 0** — uv 환경, DuckDB 11 테이블, CLI scaffolding (74 unit tests)
- [x] **Phase 1** — EDGAR 수집 파이프라인 (15명 / 110 filings / 10,867 holdings / 1,584 price tickers)
- [x] **Phase 2** — 4 시그널(diff/conviction/continuity/consensus) + 종합 점수 (10,759 signals / 8,785 total_scores)
- [x] **Phase 3** — Strategy ABC + 6 전략 + Lookahead 가드 + Engine + Runner (104 unit tests, 가용 데이터 기준 17개월 백테스트 검증)
- [x] **Phase 4** — Streamlit 5 페이지 + Quarto 6 챕터 (Phase 5에서 Streamlit은 `_legacy_dashboard/`로 격리, Quarto만 유지)
- [x] **Phase 4+** — Gemini LLM 통합 (분기 헤드라인 요약 + Top 10 시그널 해석). API 키 없으면 graceful skip
- [x] **Phase 5** — Static SPA Migration. 9페이지 React/JSX SPA + FastAPI 정적 서버 + DuckDB→JSON exporter + Gemini `/api/ask` chat + MultiManager 전략(7th) + `backtest_holdings` 테이블 + `cusip_ticker_map.sector/industry` 컬럼. 156 unit + 2 integration tests passed.

## Reference Triggers

- **디자인/스키마/공식 결정 의문 시** → read `docs/superpowers/specs/2026-05-20-13f-tracker-design.md` first
- **현행 구현 step/TDD 패턴 의문 시** → read `docs/superpowers/plans/2026-05-21-13f-tracker.md` first
- **Frontend migration(Streamlit→SPA) 진행 / 새 명령(`thirteen-f export`/`serve`) 설계** → read `docs/superpowers/plans/2026-05-22-13f-frontend-migration.md` first
- **새 디자인 토큰·페이지 인터랙션 참고** → read `handoff/design/*.jsx`, `handoff/design/hf-styles.css` (라이트 톤 Pretendard + #1d6dc8 accent, Koyfin 스타일)
- **EDGAR HTTP 규약/rate limit/value 단위** → read `참고/edgar_notes.md` first
- **DuckDB 스키마** → read `scripts/init_db.py` (single source of truth; spec과 일치)
- **사용자 실행 환경/명령** → read `README.md` + `.env.example`

## Tech Stack

Python ≥3.11 (uv) / httpx / lxml / duckdb / polars / pyyaml / typer / yfinance / rich / tenacity / pydantic v2 / fastapi + uvicorn (Phase 5) / plotly (Quarto 한정) / vcrpy (test) / Quarto CLI (선택) / Gemini API (raw httpx, 선택) / React 18 + Babel-standalone (CDN, frontend)

## Commands

```bash
uv run thirteen-f collect --start 2024Q1    # Phase 1: EDGAR + parser + CUSIP + prices
uv run thirteen-f analyze                   # Phase 2: signals + score
uv run thirteen-f backtest --all --start 2024-01-02   # Phase 3: 7 전략 백테스트 (incl. MultiManager)
uv run thirteen-f backtest --strategy ScoreTopK --start 2024-01-02
uv run thirteen-f export                    # Phase 5: DuckDB → JSON dump (web/data/)
uv run thirteen-f serve --port 8765         # Phase 5: FastAPI 정적 SPA + /api/health + /api/ask (Gemini chat)
uv run thirteen-f report --latest --open    # Quarto 6 챕터 → HTML (Quarto CLI 필요)
uv run thirteen-f update                    # 풀 오케스트레이션: collect → analyze → backtest --all → export → report
uv run thirteen-f update --skip-collect --skip-backtest --skip-export  # 단계별 skip

uv run pytest tests/unit -q                                       # 156 passed (전체)
uv run pytest tests/unit/web -v                                   # Phase 5 web 모듈만
uv run pytest tests/unit/analyze -k consensus                     # 키워드 필터
uv run pytest -m integration                                      # vcrpy + serve smoke
uv run ruff check src tests                                       # lint
uv run mypy src/thirteen_f                                        # type check

uv run python scripts/init_db.py            # 신규 클론 / 스키마 변경 시 12 테이블 재생성 (Phase 5: + backtest_holdings)
uv run python scripts/supplement.py         # one-off: slash normalize + missing prices
uv run python scripts/supplement_sector.py  # Phase 5: cusip_ticker_map.sector/industry yfinance backfill (1회)
uv run python scripts/bench_llm.py          # Gemini thinking on/off 비교 측정
```

## Module Layout (`src/thirteen_f/`)

각 모듈은 1 phase 책임을 갖고 `pipeline.py`(or `engine.py`+`runner.py`)가 단계 entrypoint를 제공한다. CLI는 thin dispatcher.

- `cli.py` — typer `app` 정의. `collect`/`analyze`/`backtest`/`export`/`serve`/`report`/`update` 서브커맨드. import는 함수 안에서 lazy.
- `core/` — `config.py`(`.env`+TOML 합성 + weights 합 검증), `dates.py`(quarter 라벨↔날짜), `logging.py`(rich + jsonl)
- `collect/` — Phase 1. `edgar_client.py`(httpx + tenacity), `parser.py`(lxml infotable), `cusip_mapper.py`(OpenFIGI), `price_loader.py`(yfinance + Stooq fallback), `pipeline.py`(orchestrator)
- `analyze/` — Phase 2. `diff.py`/`conviction.py`/`continuity.py`/`consensus.py`/`cloning_quality.py`/`concentration.py` 6 시그널 + `score.py`(weights) + `pipeline.py`
- `backtest/` — Phase 3+5. `strategy.py`(`Strategy` ABC + `BacktestResult` with `holdings_log`), `strategies/`(7 구현체 — incl. `multi_manager.py`), `engine.py`(SPY rebalance + 분기 holdings snapshot persist), `metrics.py`, `runner.py`
- `web/` — Phase 5. `schemas.py`(Pydantic JSON contract SSOT), `queries.py`(SQL helper, A1에서 dashboard/tables.py에서 이주), `exporter.py`(DuckDB → JSON dump), `server.py`(FastAPI: /api/health + /api/ask + /data + /static), `cli.py`(do_export/do_serve), `static/`(9페이지 SPA: hf-*.jsx + hf-styles.css + index.html), `ask_context.py`(질문에서 ticker/manager 추출), `data/`(.gitignore — export 결과)
- `llm/` — `gemini.py`(httpx 직접 호출, thinking + response_schema), `prompts.py`(builder + `CHAT_SCHEMA`/`chat_prompt`), `summary.py`(headline + explain + `chat_reply`). API 키 없으면 graceful skip
- `_legacy_dashboard/` — Phase 4의 Streamlit 5 페이지 격리본. Quarto가 `_legacy_dashboard.charts`(plotly)에 의존하기에 보존. 새 기능 추가 금지.

## Project Layout (top-level)

- `config/` — `managers.yaml`(15명 CIK+label+style), `scoring.toml`(weights), `analysis.toml`(threshold)
- `scripts/` — `init_db.py`(schema SSOT), `supplement.py`(post-collect fixup), `bench_llm.py`(thinking 비교)
- `reports/quarto/` — `index.qmd` + `01_overview.qmd ~ 05_data_quality.qmd` (6 챕터), `_common.py`(DuckDB 헬퍼). 출력은 `reports/output/<quarter>/`
- `tests/` — `unit/`(74+ 모듈 단위) · `integration/`(vcrpy 카세트 — `tests/fixtures/`에 cassette 저장)
- `handoff/design/` — Phase 5 frontend 디자인 reference (정적 HTML/JSX/CSS, mock 포함). production은 `src/thirteen_f/web/static/`로 복사됨 — 수정은 그쪽에서만.
- `_claude_docs/` — `FRONTEND_PARITY.md` (data 항목별 backend/frontend 계산 위치 매트릭스)
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design spec + TDD plan (single source of truth for 의사결정)
- `참고/` — 초기 사전 조사 노트 (`PLAN.md`, `edgar_notes.md`, `schema.md`)
- `data/` — DuckDB + 로그 (git ignored)

## Key Design Decisions

- **Lookahead bias 차단** (Spec §7.4): 백테스트 SQL에 `filings.filed_at <= as_of_date` 강제
- **value 단위 normalize** (Spec §5.3): SEC 2023-01-03 경계 — 이전 천 달러, 이후 달러
- **CUSIP → ticker** (Spec §5.1-1e): OpenFIGI US primary 거래소(UN/UQ/UR/UP/UA/UF/UV/UW/UD/US)만, 슬래시·점 → 대시 정규화
- **정정본** (Spec §5.2): 같은 (cik, period_of_report) 내 최신 filed_at만 superseded_by=NULL, 나머지는 최신 accession 참조
- **종합 점수 weights** (Spec §6.1): consensus 0.30 + conviction 0.30 + continuity 0.20 + cloning_quality 0.20 = 1.0 (load 시 합 검증)
- **거장 15명** (Spec §1.2): value 7 + activist 4 + macro 4 (Ray Dalio Bridgewater 포함, ETF 비중 큼)
- **holdings PK** (Spec §4.2): (accession_no, cusip, title_of_class, put_call) — NULL 회피 위해 마지막 2개는 NOT NULL DEFAULT ''
- **단일 패키지 모듈러**: `src/thirteen_f/` (core / collect / analyze / backtest / web / llm / _legacy_dashboard)
- **데이터 저장소**: DuckDB 단일 파일 `data/13f.duckdb` (커밋 금지). Phase 5: 12 테이블 (+ `backtest_holdings`)
- **Lookahead-safe MultiManager** (Plan §D1): `QUALIFY ROW_NUMBER() OVER (PARTITION BY cik ...)`로 매니저별 latest accession만 사용. 매니저별 분기 미스매치는 의도 (각자 가장 신선한 13F).

## Environment Variables (.env)

- `SEC_USER_AGENT` (필수): `"Name email@domain.com"` — SEC fair-access policy. 누락 시 403.
- `OPENFIGI_API_KEY` (선택): 무인증 25/min, 인증 250/min
- `STOOQ_API_KEY` (선택): Stooq 2024+ 무인증 폐지 — 키 없으면 fallback skip
- `DUCKDB_PATH` (기본 `data/13f.duckdb`)
- `GOOGLE_API_KEY` + `GOOGLE_MODEL=gemini-3-flash-preview` (Phase 4 분기 리포트 자연어 요약 + 시그널 해석). 미설정 시 LLM 셀은 안내 placeholder만 표시
- `GEMINI_THINKING=true|false` (기본 `true`): thinking 모델의 thinking 토글. `false` 시 `thinkingConfig.thinkingBudget=0` 강제 → 토큰·지연 ↓ 품질 미세 ↓. 실측: headline OFF 3.91s vs ON 7.44s

## Known Issues / Quirks

- **OpenFIGI 매핑률 87.3%** — 외국 거래소·warrants·private securities 제외 후 의도된 수치 (DoD 90% 미달이지만 backtest 의미 충족)
- **가격 누락 13 ticker** — AKRO, AMED, CADE, CDTX, CIVI, CMA, DNB, HES, PCH, WBA (delisted/merged) + FLYX-WS/NPWR-WS/OXY-WS (warrants). backtest 시 해당 종목만 skip
- **Buffett "No info table XML"** — 일부 13F-HR이 Confidential Treatment 또는 13F-NT 형태로 보고된 정상 경고. 결과적으로 `SingleManagerClone(Buffett)` 백테스트는 가용 holdings가 거의 없어 NAV 변동 ≈ 0 (코드 버그 아닌 데이터 한계)
- **백테스트 가용 범위** — 가격 데이터가 2024-01-02부터라 plan 예시 `--start 2015-01-01`은 자동으로 2024-01-02부터 수행됨 (SPY 영업일 기준). 17개월(2024-01-02 ~ 2026-05-20)이라 long-cycle 검증 부족 — 데이터 더 쌓이면 재검증 필요
- **NewBuyOnly CAGR 39.74%** — 17개월 백테스트에서 small-cap 신규매수 consensus rotation 효과로 과대 노출 가능성. 표본 기간 짧고 fee/slippage 가정 단순(편도 10bp)이라 실거래 재현성 ≠ 동일. 더 긴 기간·실제 비용 모델로 재검증 필요
- **Nygren CIK** — `company_tickers.json`에 ticker 없는 13F-only filer라 resolve_cik 실패. yaml에 직접 `0000813917` 입력 (Harris Associates L P)
- **pandas-datareader 0.10** — pandas 3.0과 비호환. Stooq는 httpx 직접 호출로 교체됨
- **Quarto CLI 시스템 의존성** — `uv run thirteen-f report`는 OS-level `quarto` 실행 파일 필요. Windows: `winget install RStudio.Quarto`. 미설치 시 명령은 안내 메시지 후 exit 2
- **Gemini thinking 모델 토큰 한도** — `gemini-3-flash-preview` 같은 thinking 모델은 `max_output_tokens`를 thinking 토큰과 응답 토큰이 함께 나눠 쓴다. thinking ON에서 한도를 크게 잡아야 답변이 잘리지 않음. 현재 `llm/gemini.py:generate(max_output_tokens=8192, enable_thinking=True)` 기본값. headline 호출 4096, explain·chat 호출 8192. thinking on/off는 `.env`의 `GEMINI_THINKING` 또는 함수 인자 `enable_thinking`으로 제어
- **backtest_holdings 마이그레이션** — Phase 5에서 신설. 기존 backtest run은 holdings_log 비어있음 — `uv run thirteen-f backtest --all` 재실행 권장
- **cusip_ticker_map.sector backfill** — Phase 5에서 sector/industry 컬럼 신설. `uv run python scripts/supplement_sector.py` 1회 실행 필요 — 미실행 시 stocks.json의 sector가 모두 "Other"라 treemap 색 단조로움
- **`thirteen-f dashboard` 명령 제거** — Phase 5에서 삭제. Streamlit 사용 시 `_legacy_dashboard/app.py`를 직접 streamlit run으로 호출 가능하나 권장 안 함. `thirteen-f serve` 사용

## Workflow Rules

- **Phase 진행** — 한 Phase 끝에서 멈춰 DoD 충족 확인 후 사용자 승인 → 다음 Phase
- **TDD** — test 작성 → fail 확인 → 최소 구현 → pass → commit (Plan의 step 단위)
- **개별 git add** — `git add .` 금지, 명시적 파일만 stage
- **.env 커밋 금지** — `.gitignore`에 포함
- **destructive 명령 전 확인** — 사용자 확인 없이 `rm -rf`, `git reset --hard` 등 금지

## When doing X → read Y first

- **백테스트 전략 추가** → Spec §7.2 (Strategy ABC) + Plan Chunk 4 (Tasks 3.x)
- **새 시그널 추가** → Spec §6.1 + Plan Chunk 3 (Tasks 2.x), 점수 weights 합 1.0 유지
- **Phase 진행 / 다음 task** → Plan의 해당 Chunk 절 + DoD 체크리스트
- **수집 후 데이터 부족 / 매핑 실패** → `scripts/supplement.py` 패턴 (post-collect fixup)
- **DuckDB 스키마 변경** → `scripts/init_db.py` 먼저 수정 후 코드 / Spec §4.2 동기화
- **LLM prompt 수정 / 새 챕터 추가** → `src/thirteen_f/llm/prompts.py` (prompt builder) + `src/thirteen_f/llm/summary.py` (DB fetch). Quarto 셀에서 `enable_thinking=_settings.gemini_thinking` 전달 유지
- **Gemini 응답 잘림** → finishReason / `usageMetadata.thoughtsTokenCount` 확인 (`scripts/bench_llm.py`). thinking ON일 때 `max_output_tokens`를 충분히 크게 (headline 4096+ / explain 8192+)
- **Frontend SPA 수정** → `src/thirteen_f/web/static/`에서만 수정 (`handoff/design/`은 read-only reference). 데이터 계산 위치 의문 → `_claude_docs/FRONTEND_PARITY.md`
- **새 시그널·전략 데이터를 frontend로 노출** → `web/exporter.py`에 export_* 함수 추가 + `web/schemas.py`에 Pydantic 모델 + frontend는 `hf-data.js:bootstrapFromJson` Promise.all 항목 추가
- **새 CLI 서브커맨드 추가** → `src/thirteen_f/cli.py`의 패턴 따름 (import는 함수 안에서 lazy, OptionInfo 직접 호출 금지 — `update` 처럼 subprocess로 위임)
- **`/api/ask` prompt/스키마 수정** → `llm/prompts.py` `chat_prompt`/`CHAT_SCHEMA` + `web/ask_context.py:build_context` (질문 → DB context)

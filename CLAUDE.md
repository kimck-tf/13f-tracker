# 13F Portfolio Tracker — Project Guide

미국 투자 거장 15명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## Status (as of 2026-05-21)

- [x] **Phase 0** — uv 환경, DuckDB 11 테이블, CLI scaffolding (74 unit tests)
- [x] **Phase 1** — EDGAR 수집 파이프라인 (15명 / 110 filings / 10,867 holdings / 1,584 price tickers)
- [x] **Phase 2** — 4 시그널(diff/conviction/continuity/consensus) + 종합 점수 (10,759 signals / 8,785 total_scores)
- [x] **Phase 3** — Strategy ABC + 6 전략 + Lookahead 가드 + Engine + Runner (104 unit tests, 가용 데이터 기준 17개월 백테스트 검증)
- [ ] **Phase 4** — Streamlit 대시보드 + Quarto 분기 리포트 (Gemini LLM 보조)

## Reference Triggers

- **디자인/스키마/공식 결정 의문 시** → read `docs/superpowers/specs/2026-05-20-13f-tracker-design.md` first
- **구현 step/TDD 패턴 의문 시** → read `docs/superpowers/plans/2026-05-21-13f-tracker.md` first
- **EDGAR HTTP 규약/rate limit/value 단위** → read `참고/edgar_notes.md` first
- **DuckDB 스키마** → read `scripts/init_db.py` (single source of truth; spec과 일치)
- **사용자 실행 환경/명령** → read `README.md` + `.env.example`

## Tech Stack

Python ≥3.11 (uv) / httpx / lxml / duckdb / polars / pyyaml / typer / yfinance / streamlit / plotly / rich / tenacity / vcrpy (test) / Quarto CLI (Phase 4)

## Commands

```bash
uv run thirteen-f collect --start 2024Q1    # Phase 1: EDGAR + parser + CUSIP + prices
uv run thirteen-f analyze                   # Phase 2: signals + score
uv run thirteen-f backtest --all --start 2024-01-02   # Phase 3: 6 전략 백테스트 (CAGR/MDD/Sharpe 출력)
uv run thirteen-f backtest --strategy ScoreTopK --start 2024-01-02
uv run thirteen-f dashboard                 # Phase 4 (TODO)
uv run thirteen-f report --latest --open    # Phase 4 (TODO)

uv run pytest tests/unit -q                 # 104 passed
uv run python scripts/supplement.py         # one-off: slash normalize + missing prices
```

## Key Design Decisions

- **Lookahead bias 차단** (Spec §7.4): 백테스트 SQL에 `filings.filed_at <= as_of_date` 강제
- **value 단위 normalize** (Spec §5.3): SEC 2023-01-03 경계 — 이전 천 달러, 이후 달러
- **CUSIP → ticker** (Spec §5.1-1e): OpenFIGI US primary 거래소(UN/UQ/UR/UP/UA/UF/UV/UW/UD/US)만, 슬래시·점 → 대시 정규화
- **정정본** (Spec §5.2): 같은 (cik, period_of_report) 내 최신 filed_at만 superseded_by=NULL, 나머지는 최신 accession 참조
- **종합 점수 weights** (Spec §6.1): consensus 0.30 + conviction 0.30 + continuity 0.20 + cloning_quality 0.20 = 1.0 (load 시 합 검증)
- **거장 15명** (Spec §1.2): value 7 + activist 4 + macro 4 (Ray Dalio Bridgewater 포함, ETF 비중 큼)
- **holdings PK** (Spec §4.2): (accession_no, cusip, title_of_class, put_call) — NULL 회피 위해 마지막 2개는 NOT NULL DEFAULT ''
- **단일 패키지 모듈러**: `src/thirteen_f/` (core / collect / analyze / backtest / dashboard)
- **데이터 저장소**: DuckDB 단일 파일 `data/13f.duckdb` (커밋 금지)

## Environment Variables (.env)

- `SEC_USER_AGENT` (필수): `"Name email@domain.com"` — SEC fair-access policy. 누락 시 403.
- `OPENFIGI_API_KEY` (선택): 무인증 25/min, 인증 250/min
- `STOOQ_API_KEY` (선택): Stooq 2024+ 무인증 폐지 — 키 없으면 fallback skip
- `DUCKDB_PATH` (기본 `data/13f.duckdb`)
- `GOOGLE_API_KEY` + `GOOGLE_MODEL=gemini-3-flash-preview` (Phase 4 분기 리포트 자연어 요약 + 시그널 해석)

## Known Issues / Quirks

- **OpenFIGI 매핑률 87.3%** — 외국 거래소·warrants·private securities 제외 후 의도된 수치 (DoD 90% 미달이지만 backtest 의미 충족)
- **가격 누락 13 ticker** — AKRO, AMED, CADE, CDTX, CIVI, CMA, DNB, HES, PCH, WBA (delisted/merged) + FLYX-WS/NPWR-WS/OXY-WS (warrants). backtest 시 해당 종목만 skip
- **Buffett "No info table XML"** — 일부 13F-HR이 Confidential Treatment 또는 13F-NT 형태로 보고된 정상 경고. 결과적으로 `SingleManagerClone(Buffett)` 백테스트는 가용 holdings가 거의 없어 NAV 변동 ≈ 0 (코드 버그 아닌 데이터 한계)
- **백테스트 가용 범위** — 가격 데이터가 2024-01-02부터라 plan 예시 `--start 2015-01-01`은 자동으로 2024-01-02부터 수행됨 (SPY 영업일 기준). 17개월(2024-01-02 ~ 2026-05-20)이라 long-cycle 검증 부족 — 데이터 더 쌓이면 재검증 필요
- **NewBuyOnly CAGR 39.74%** — 17개월 백테스트에서 small-cap 신규매수 consensus rotation 효과로 과대 노출 가능성. 표본 기간 짧고 fee/slippage 가정 단순(편도 10bp)이라 실거래 재현성 ≠ 동일. 더 긴 기간·실제 비용 모델로 재검증 필요
- **Nygren CIK** — `company_tickers.json`에 ticker 없는 13F-only filer라 resolve_cik 실패. yaml에 직접 `0000813917` 입력 (Harris Associates L P)
- **pandas-datareader 0.10** — pandas 3.0과 비호환. Stooq는 httpx 직접 호출로 교체됨

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

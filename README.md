# 13F Portfolio Tracker

미국 투자 거장 14명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## What it does

- **수집**: SEC EDGAR에서 분기별 13F-HR 공시 직접 파싱 (httpx + lxml)
- **분석**: 분기 간 변화·conviction·continuity·consensus 4 시그널 + 가중 종합 점수
- **백테스트**: 7종 전략 8개 구성 (SingleManagerClone(Buffett·Druckenmiller) / ConsensusTopK / ScoreTopK / ConvictionFollow / NewBuyOnly / Ensemble / **MultiManager**) + Lookahead-safe 검증 + 분기 holdings snapshot
- **시각화**: 10페이지 정적 SPA (Home / Managers / Compare / Stocks / Changes / Consensus / Backtest / **Plan** / Builder / Ask) — React 18 + Pretendard, FastAPI 정적 서버. Plan은 백테스트 비교 → 권장 전략 → 지금의 목표 비중·매수/매도 목록
- **리포트**: Quarto 6 챕터 단일 HTML (선택: Gemini LLM 분기 헤드라인 요약 + Top 10 시그널 해석)
- **Ask LLM**: `/api/ask` 엔드포인트 (Gemini chat with structured cards, per-IP rate limit 10/min, prompt injection 방어)

## Tracked Managers (14)

| 스타일 | 거장 (13F 제출 법인이 이름과 다른 경우 괄호) |
|---|---|
| Value / Quality (6) | Buffett, Klarman, Akre, Li Lu, Pabrai (Dalal Street), Nygren (Harris Associates) |
| Activist (4) | Ackman (+ Pershing Square Inc.), Loeb, Einhorn (DME Capital Management), Icahn |
| Macro / Contrarian (4) | Tepper, Druckenmiller, Burry, Dalio |

> ⚠️ **명단 정리 (2026-09-15)** — Klarman·Einhorn·Pabrai는 CIK가 다른 엔터티(Lone Pine Capital, Greenlight Capital Re, 개인 CIK)를 가리키던 것을 바로잡았고, Ackman은 2026Q2부터 보유내역을 신고하는 Pershing Square Inc.의 13F를 함께 수집한다. Greenblatt(Gotham Asset Management)은 1,791종목 시스템 운용 장부라 편입하면 3명 이상 보유 종목이 39개 → 186개로 늘어 컨센서스 신호를 흐리므로 제외했다. Burry(Scion)는 2025Q3 이후 13F가 없어 과거 데이터만 있다.

## Setup

```bash
# 1) Python 환경 (uv 필요)
uv venv
uv sync

# 2) .env (SEC fair-access policy)
cp .env.example .env
# .env 편집:
#   SEC_USER_AGENT="Your Name email@domain.com"   (필수)
#   GOOGLE_API_KEY="..."                          (선택, LLM 요약/해석 활성화)
#   GEMINI_THINKING="true"                        (선택, 기본 true)

# 3) DuckDB 12 테이블 초기화 (Phase 5: + backtest_holdings)
uv run python scripts/init_db.py

# 4) (선택) Quarto CLI 설치 — 분기 HTML 리포트용
#   Windows:  winget install RStudio.Quarto
#   macOS:    brew install --cask quarto
#   미설치 시 serve / backtest 는 정상, report 만 안내 후 종료
```

## Run the App (Phase 5)

```bash
# 1) 전체 파이프라인 한 번 (collect → analyze → backtest → export → report)
#    update는 collect를 --start 없이 실행해 2011Q1부터 수집한다. 기존 범위(2024Q1~)를 유지하려면
#    uv run thirteen-f collect --start 2024Q1  →  uv run thirteen-f update --skip-collect
uv run thirteen-f update

# 2) (선택) cusip_ticker_map.sector backfill — 신규 ticker 추가 후 1회
uv run python scripts/supplement_sector.py

# 3) 정적 서버 부팅 — http://localhost:8765
uv run thirteen-f serve

# JSON dump만 다시 만들고 싶을 때 (DB는 그대로)
uv run thirteen-f export
```

## Quick Start

```bash
# Phase 1: EDGAR 분기 수집 (약 2시간 — 대부분 전 종목 가격 다운로드, 2026-09 실측)
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

- [x] Phase 0 — 환경 셋업, DuckDB 12 테이블 (Phase 5: +`backtest_holdings`), CLI scaffolding
- [x] Phase 1 — EDGAR 수집 (15명 / 110 filings / 10,867 holdings / 1,584 price tickers)
- [x] Phase 2 — 4 시그널 + 종합 점수 (10,759 signals / 8,785 total_scores)
- [x] Phase 3 — Strategy ABC + 7 전략(MultiManager 추가) + Lookahead-safe + Engine + Runner
- [x] Phase 4 — Quarto 6 챕터 + report CLI (Streamlit 5페이지는 `_legacy_dashboard/`로 격리)
- [x] Phase 4+ — Gemini LLM 통합 (분기 헤드라인 요약 + Top 10 시그널 해석, thinking on/off 토글)
- [x] Phase 5 — Static SPA (9페이지) + FastAPI 정적 서버 + DuckDB→JSON exporter + Gemini `/api/ask` chat + per-IP rate limit
- [x] Phase 5 Code Review Fix — 12 finding 반영 (4 Critical + 8 Important): BACKTESTS 정밀 매칭 + SIM 배지, rate_limit GC, TICKER stop-list, export_stocks SQL 최적화(MAX_BY), chat_prompt injection 방어, ErrorScreen 친화 진단 등
- [x] 2026Q2 반영 (2026-09-15) — 14명 중 13명 2026Q2 13F 수집 (138 filings / 13,008 holdings / 1,817 price tickers, 가격 2026-09-14까지). 명단 교정: Klarman·Einhorn·Pabrai CIK 수정, Greenblatt 제외, Ackman은 `extra_ciks`로 Pershing Square Inc. 합산. 수집 버그 수정: Berkshire information table 누락, NEW HOLDINGS 정정이 원본을 가림, NaN 가격 저장, CINS 코드(Chubb·Accenture·Linde 등 외국 소재 미국 상장사 130종목) 미매핑(매핑률 87.3% → 93.3%). 티커 변경 5건 매핑 갱신(BK→BNY 등). Buffett과 비교할 `SingleManagerClone(Druckenmiller)`를 기본 백테스트에 추가하고, 복제 전략이 같은 티커의 주식·옵션 행을 덮어쓰던 버그를 수정(합산, 풋 제외)

- [x] 백테스트 최적화 (2026-09-20) — 벤치마크 NAV 갱신·집계형 lookahead 규칙·NewBuyOnly `min_positions` 수정 후 79개 설정 탐색(`scripts/sweep_backtests.py`, DB 사본). Calmar 기준 1위 ConsensusTopK(3,10)을 비롯한 계열별 최적값을 기본 스위트에 반영. 보고서 `docs/backtest-optimization-2026-09.md`. `thirteen-f targets` 명령과 SPA **Plan** 탭(비교표 → 권장 전략 → 지금의 목표 비중·매수/매도 목록, `targets.json`) 추가

**unit 189 passed · integration 3 passed + 1 skipped** (collect e2e는 로컬 VCR 카세트를 `RECORD_VCR=1`로 녹화해야 실행). (Frontend SPA는 단위 테스트 X — `thirteen-f serve` 후 브라우저 navigate 검증; LLM은 httpx mock + structured JSON schema 검증; Quarto는 사용자 CLI 설치 후 검증)

## Backtest Snapshot (2024-01-02 ~ 2026-09-14, cost_bps=10, 2026-09-20 실행)

기본 8전략의 파라미터는 2026-09 탐색(`docs/backtest-optimization-2026-09.md`, 79개 설정, Calmar 기준)의 계열별 최적값이다. "이전 설정" 열은 탐색 전 파라미터로 2026-09-15에 실행한 값.

| 전략 | CAGR | MDD | Sharpe | Calmar | 이전 설정 → CAGR |
|---|--:|--:|--:|--:|---|
| SingleManagerClone(Buffett) | 16.20% | 20.50% | 1.06 | 0.79 | 같음 → 16.20% |
| SingleManagerClone(Druckenmiller) | 35.95% | 26.15% | 1.48 | 1.37 | 같음 → 35.95% |
| **ConsensusTopK(3, 10)** — 탐색 1위 | **29.93%** | **15.93%** | 1.57 | **1.88** | ConsensusTopK(3, 20) → 21.59% |
| ScoreTopK(40) | 19.67% | 18.85% | 1.24 | 1.04 | ScoreTopK(20) → 16.40% |
| ConvictionFollow(3) | 21.79% | 18.43% | 1.35 | 1.18 | ConvictionFollow(10) → 15.39% |
| NewBuyOnly(2, 15) | 39.59% | 31.79% | 1.10 | 1.25 | 같음 → 36.17% (lookahead 규칙 변경으로 달라짐) |
| Ensemble(ConsensusTopK(3,10) 0.5 / ConsensusTopK(2,15) 0.5) | 28.28% | 15.77% | 1.59 | 1.79 | Ensemble(Buffett 0.4 / ScoreTopK 0.4 / ConsensusTopK 0.2) → 17.32% |
| MultiManager(Burry·Dalio·Druckenmiller·Tepper, 20) | 33.06% | 23.76% | 1.34 | 1.39 | MultiManager(Buffett·Ackman·Tepper, 15) → 14.41% |

같은 기간 SPY CAGR은 20.72%다 (모든 전략에 같은 값 — 벤치마크 NAV를 첫 매수 전에도 갱신하도록 엔진을 고쳤다). 탐색 보고서는 첫 13F 공개일(2024-05-13)부터 계산해 수치가 이 표보다 높다(예: ConsensusTopK(3,10) CAGR 35.3%).

### ⚠️ 해석 주의사항

1. **이전 스냅샷의 `SingleManagerClone(Buffett)` CAGR 0%는 데이터 한계가 아니라 수집 버그였다**
   Berkshire 제출물의 information table 파일명(`56757.xml` 같은 숫자 이름)을 찾지 못해 보유내역이 전부 빠졌고, 2025Q1은 NEW HOLDINGS 정정(4종목)이 원본(110건)을 가렸다. 2026-09에 수정했다. 같은 때 외국 소재 미국 상장사(Chubb·Accenture·Linde 등 CINS 코드 130종목)가 매핑되지 않던 버그를 고치고 매니저 명단(Klarman·Einhorn·Pabrai CIK, Greenblatt 제외, Ackman 법인 변경)을 바로잡아, 2026-05 스냅샷과 대부분의 전략 수치가 달라졌다.

2. **`NewBuyOnly`는 추천하지 않는다** — 2명 이상 신규매수 후보가 분기당 1~8종목뿐이라 NVDA 100%(2025-07), AER 100%(2026-04) 같은 단일 종목 분기가 있고, CAGR 39.59%·MDD 31.79%는 종목 두세 개의 결과다. 화면 비교용으로만 남겼다. 편도 10bp 거래비용 가정은 어느 전략이든 단순하고 slippage·세금·차입 제한 미반영.

3. **백테스트 가용 시작일은 2024-01-02** (SPY 가격 데이터 시작점)
   첫 13F(2024Q1)가 2024-05-13에 공개돼 그 전까지는 모든 전략이 현금이고, 그만큼 CAGR이 SPY보다 불리하게 계산된다. 약 32개월 short-cycle 검증이지 long-cycle 검증이 아니다. 파라미터는 이 표본 안에서 고른 값이라 실제 기대 성과는 표보다 낮게 봐야 한다.

4. **Buffett vs Druckenmiller 복제** — 두 복제 모두 첫 13F가 보이는 2024-05-15부터 투자한다. Druckenmiller 복제(누적 +128%)는 Natera(비중 13~18%)·Insmed·Teva 같은 소수 고확신 종목이 성과를 주도했고, 2025-04 관세 충격 때 하루 −7.7%·+12.9%로 변동도 크다. 복제는 콜옵션을 기초자산 명목금액의 롱 노출로 계산하고(분기별 비중 2.6~16.4%) 풋은 제외하므로, 레버리지·프리미엄이 있는 실제 포지션과 다르다. Duquesne이 금액을 천 달러 단위로 보고하는 문제는 제출물 안의 상대 비중만 쓰는 복제 수익률에는 영향이 없다.

5. **매니저 구성** — Burry(Scion)는 2025Q3 이후 13F가 없어 최근 분기 컨센서스에서 빠진다. Ackman의 2026Q2는 Pershing Square Inc. 통합 보고라 HHH +900만 주, PSUS 신규처럼 법인이 직접 보유하던 지분이 합쳐져 보이는 변화가 섞여 있다(실제 매매 아님).

6. **Lookahead bias 차단은 검증됨** (Spec §7.4)
   5개 전략 × 미래 filing 노출 6 케이스 단위 테스트로 확인. `filings.filed_at <= as_of_date` 가드는 모든 전략 SQL에 강제됨. 매니저 전원의 집계(총점·컨센서스)를 쓰는 전략은 그 분기 13F가 모두 제출된 뒤에만 그 분기를 쓴다 (2026-09 수정 전에는 첫 제출자 기준이라 최대 11일 앞섰다).

7. **탐색에서 발견한 정의상 한계** — 컨센서스 상위 종목에 GOOG·GOOGL이 따로 들어가 Alphabet이 사실상 두 자리를 차지하고, SPY 같은 ETF도 종목으로 집계된다. 같은 회사 복수 클래스 합산·ETF 제외는 아직 없다 (`docs/backtest-optimization-2026-09.md` §5·§6).

## LLM 보조 (선택)

`.env`에 `GOOGLE_API_KEY` 입력 시 Quarto 리포트의 `index.qmd`와 `03_signals.qmd`가 Gemini를 호출하여 자동으로 한국어 요약 생성. API 키 없으면 placeholder 안내만 표시 — 다른 기능에는 영향 없음.

- **`index.qmd`** — 분기 헤드라인 요약 (5문장 이내, 데이터 직접 인용)
- **`03_signals.qmd`** — Top 10 종목 시그널 해석 (점수 강약, 매수 매도 권고 금지)

### Thinking on/off

| 설정 | 응답 시간 (headline) | 토큰 사용 | 품질 |
|---|--:|--:|---|
| `GEMINI_THINKING="true"` (기본) | ~7.4s | thinking ~750 + 응답 ~190 | thinking으로 답변 정돈 |
| `GEMINI_THINKING="false"` | ~3.9s | thinking 0 + 응답 ~220 | 비교 가능, 약간 풍부 |

함수 인자 `enable_thinking=False`로 호출 단위 override도 가능.

## CLI Commands

| Command | Phase | Status |
|---|---|---|
| `thirteen-f collect [--start QUARTER]` | 1 | done |
| `thirteen-f analyze [--threshold FLOAT]` | 2 | done |
| `thirteen-f backtest [--strategy NAME / --all] [--start --end --cost-bps]` | 3 | done (기본 8개: 7종 전략 + Druckenmiller 복제) |
| `thirteen-f targets --strategy NAME [--as-of DATE]` | 3 | done (전략이 지금 지시하는 목표 비중 — 분기마다 매매 목록 확인) |
| `thirteen-f export [--out DIR]` | 5 | done (DuckDB → JSON dump for SPA, `targets.json` 포함) |
| `thirteen-f serve [--host --port --reload]` | 5 | done (FastAPI 정적 SPA on :8765) |
| `thirteen-f report [--quarter Q / --latest] [--open]` | 4 | done (Quarto CLI 필요) |
| `thirteen-f update [--skip-collect / --skip-backtest / --skip-export / --skip-report]` | all | done |

## Tech Stack

**Backend**: Python ≥ 3.11 / uv / httpx / lxml / duckdb / polars / pyyaml / typer / yfinance / rich / tenacity / pydantic v2 / fastapi + uvicorn (Phase 5) / plotly (Quarto 전용)
**Frontend**: React 18 + Babel-standalone (CDN) / Pretendard + JetBrains Mono / hash router SPA
**Optional**: Quarto CLI (HTML 리포트) / Gemini API raw httpx (LLM 요약·해석·chat)

## Design References

- 디자인 스펙 (Phase 0~4): `docs/superpowers/specs/2026-05-20-13f-tracker-design.md`
- 구현 계획 (Phase 0~4): `docs/superpowers/plans/2026-05-21-13f-tracker.md`
- 구현 계획 (Phase 5 SPA migration): `docs/superpowers/plans/2026-05-22-13f-frontend-migration.md`
- Frontend/backend 데이터 계산 위치: `_claude_docs/FRONTEND_PARITY.md`
- Frontend 디자인 reference: `handoff/design/` (9페이지 prototype, read-only)
- 사전 조사: `참고/` (PLAN.md, edgar_notes.md, schema.md)
- 에이전트 가이드: `CLAUDE.md` + `_claude_docs/` (ARCHITECTURE · DATA_FORMATS · WORKFLOWS · TROUBLESHOOTING)

## 13F Data Limitations

1. **45일 지연** — 공개 시점엔 포지션이 변경되어 있을 수 있음
2. **롱 온리** — 숏/헤지/장외 파생 미공개
3. **미국 상장 주식만** — 해외주·채권·현금·사모 제외
4. **분기 스냅샷** — 분기 중간 매매는 보이지 않음
5. **Confidential Treatment** — 일부 거장은 보유 종목을 일정 기간 비공개 유지 가능 (Buffett 사례 다수)

이는 13F 데이터의 본질적 한계이며 백테스트 해석 시 반드시 고려해야 합니다.

## License

Personal use.

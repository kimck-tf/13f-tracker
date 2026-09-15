# 13F Portfolio Tracker

미국 투자 거장 14명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## What it does

- **수집**: SEC EDGAR에서 분기별 13F-HR 공시 직접 파싱 (httpx + lxml)
- **분석**: 분기 간 변화·conviction·continuity·consensus 4 시그널 + 가중 종합 점수
- **백테스트**: 7종 전략 8개 구성 (SingleManagerClone(Buffett·Druckenmiller) / ConsensusTopK / ScoreTopK / ConvictionFollow / NewBuyOnly / Ensemble / **MultiManager**) + Lookahead-safe 검증 + 분기 holdings snapshot
- **시각화**: 9페이지 정적 SPA (Home / Managers / Compare / Stocks / Changes / Consensus / Backtest / Builder / Ask) — React 18 + Pretendard, FastAPI 정적 서버
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

**unit 175 passed · integration 3 passed + 1 skipped** (collect e2e는 로컬 VCR 카세트를 `RECORD_VCR=1`로 녹화해야 실행). (Frontend SPA는 단위 테스트 X — `thirteen-f serve` 후 브라우저 navigate 검증; LLM은 httpx mock + structured JSON schema 검증; Quarto는 사용자 CLI 설치 후 검증)

## Backtest Snapshot (2024-01-02 ~ 2026-09-14, cost_bps=10, 2026-09-15 실행)

| 전략 | CAGR | MDD | Sharpe | 이전(2026-05) CAGR |
|---|--:|--:|--:|--:|
| SingleManagerClone(Buffett) | 16.20% | 20.50% | 1.06 | 0.00% |
| SingleManagerClone(Druckenmiller) | 35.95% | 26.15% | 1.48 | — (신규) |
| ConsensusTopK(3, 20) | 21.59% | 18.03% | 1.34 | 14.87% |
| ScoreTopK(20) | 16.40% | 23.01% | 1.03 | 24.46% |
| ConvictionFollow(10) | 15.39% | 19.07% | 1.04 | 16.10% |
| NewBuyOnly(2, 15) | 36.17% | 31.93% | 1.03 | 39.74% |
| Ensemble(Buffett 0.4 / ScoreTopK 0.4 / ConsensusTopK 0.2) | 17.32% | 20.50% | 1.17 | 19.41% |
| MultiManager(Buffett·Ackman·Tepper, 15) | 14.41% | 14.49% | 1.12 | 20.78% |

같은 기간 SPY CAGR은 약 16.3%다.

### ⚠️ 해석 주의사항

1. **이전 스냅샷의 `SingleManagerClone(Buffett)` CAGR 0%는 데이터 한계가 아니라 수집 버그였다**
   Berkshire 제출물의 information table 파일명(`56757.xml` 같은 숫자 이름)을 찾지 못해 보유내역이 전부 빠졌고, 2025Q1은 NEW HOLDINGS 정정(4종목)이 원본(110건)을 가렸다. 2026-09에 수정했다. 같은 때 외국 소재 미국 상장사(Chubb·Accenture·Linde 등 CINS 코드 130종목)가 매핑되지 않던 버그를 고치고 매니저 명단(Klarman·Einhorn·Pabrai CIK, Greenblatt 제외, Ackman 법인 변경)을 바로잡아, 이전 스냅샷과 대부분의 전략 수치가 달라졌다. MultiManager가 20.78% → 14.41%로 내려간 것은 Buffett 보유가 처음 반영돼 상위 종목 구성이 바뀌었기 때문이다.

2. **`NewBuyOnly` CAGR 36.17%는 과대 노출 가능성**
   짧은 표본에서 small-cap 신규매수 consensus rotation 효과가 부풀려졌을 수 있고 MDD도 31.93%로 가장 크다. 편도 10bp 거래비용 가정도 단순하고 slippage·세금·차입 제한 미반영. → 더 긴 기간 데이터가 쌓이면 재검증 필요.

3. **백테스트 가용 시작일은 2024-01-02** (SPY 가격 데이터 시작점)
   첫 13F(2024Q1)가 2024-05-13에 공개돼 그 전까지는 모든 전략이 현금이다. 약 32개월 short-cycle 검증이지 long-cycle 검증이 아니다. 엔진이 전략의 첫 매수 전 구간에는 SPY 수익률도 반영하지 않아 전략별 SPY CAGR이 15.6~16.3%로 조금씩 다르다.

4. **Buffett vs Druckenmiller 복제** — 두 복제 모두 첫 13F가 보이는 2024-05-15부터 투자한다. Druckenmiller 복제(누적 +128%)는 Natera(비중 13~18%)·Insmed·Teva 같은 소수 고확신 종목이 성과를 주도했고, 2025-04 관세 충격 때 하루 −7.7%·+12.9%로 변동도 크다. 복제는 콜옵션을 기초자산 명목금액의 롱 노출로 계산하고(분기별 비중 2.6~16.4%) 풋은 제외하므로, 레버리지·프리미엄이 있는 실제 포지션과 다르다. Duquesne이 금액을 천 달러 단위로 보고하는 문제는 제출물 안의 상대 비중만 쓰는 복제 수익률에는 영향이 없다.

5. **매니저 구성** — Burry(Scion)는 2025Q3 이후 13F가 없어 최근 분기 컨센서스에서 빠진다. Ackman의 2026Q2는 Pershing Square Inc. 통합 보고라 HHH +900만 주, PSUS 신규처럼 법인이 직접 보유하던 지분이 합쳐져 보이는 변화가 섞여 있다(실제 매매 아님).

6. **Lookahead bias 차단은 검증됨** (Spec §7.4)
   5개 전략 × 미래 filing 노출 6 케이스 단위 테스트로 확인. `filings.filed_at <= as_of_date` 가드는 모든 전략 SQL에 강제됨.

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
| `thirteen-f export [--out DIR]` | 5 | done (DuckDB → JSON dump for SPA) |
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

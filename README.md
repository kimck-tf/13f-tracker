# 13F Portfolio Tracker

미국 투자 거장 14명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## What it does

- **수집**: SEC EDGAR에서 분기별 13F-HR 공시 직접 파싱 (httpx + lxml)
- **분석**: 분기 간 변화·conviction·continuity·consensus 4 시그널 + 가중 종합 점수
- **백테스트**: 7종 전략 8개 구성 (SingleManagerClone(Buffett·Druckenmiller) / ConsensusTopK / ScoreTopK / ConvictionFollow / NewBuyOnly / Ensemble / **MultiManager**) + Lookahead-safe 검증 + 분기 holdings snapshot. Backtest 화면은 `backtest --all`이 남긴 backend run만 표시한다
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
uv sync --extra report   # report extra = Quarto 리포트용 jupyter·plotly (빼도 수집·분석·SPA는 동작)

# 2) .env (SEC fair-access policy)
cp .env.example .env
# .env 편집:
#   SEC_USER_AGENT="Your Name email@domain.com"   (필수)
#   GOOGLE_API_KEY="..."                          (선택, LLM 요약/해석 활성화)
#   GEMINI_THINKING="true"                        (선택, 기본 true)

# 3) DuckDB 13 테이블 초기화 (Phase 5: + backtest_holdings, 2026-11: + target_log)
uv run python scripts/init_db.py

# 4) (선택) Quarto CLI 설치 — 분기 HTML 리포트용
#   Windows:  winget install RStudio.Quarto
#   macOS:    brew install --cask quarto
#   미설치 시 serve / backtest 는 정상, report 만 안내 후 종료
```

## Run the App (Phase 5)

```bash
# 1) 전체 파이프라인 한 번 (collect → analyze → backtest → export → report)
#    update의 collect는 DB에 있는 가장 이른 분기부터 수집한다 (빈 DB면 2011Q1).
#    범위를 바꾸려면 uv run thirteen-f update --start 2020Q1
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

- [x] Phase 0 — 환경 셋업, DuckDB 13 테이블 (Phase 5: +`backtest_holdings`, 2026-11: +`target_log`), CLI scaffolding
- [x] Phase 1 — EDGAR 수집 (15명 / 110 filings / 10,867 holdings / 1,584 price tickers)
- [x] Phase 2 — 4 시그널 + 종합 점수 (10,759 signals / 8,785 total_scores)
- [x] Phase 3 — Strategy ABC + 7 전략(MultiManager 추가) + Lookahead-safe + Engine + Runner
- [x] Phase 4 — Quarto 6 챕터 + report CLI (Streamlit 5페이지는 2026-10-31에 삭제, 차트는 `reports/quarto/_charts.py`)
- [x] Phase 4+ — Gemini LLM 통합 (분기 헤드라인 요약 + Top 10 시그널 해석, thinking on/off 토글)
- [x] Phase 5 — Static SPA (9페이지) + FastAPI 정적 서버 + DuckDB→JSON exporter + Gemini `/api/ask` chat + per-IP rate limit
- [x] Phase 5 Code Review Fix — 12 finding 반영 (4 Critical + 8 Important): BACKTESTS 정밀 매칭 + SIM 배지, rate_limit GC, TICKER stop-list, export_stocks SQL 최적화(MAX_BY), chat_prompt injection 방어, ErrorScreen 친화 진단 등
- [x] 2026Q2 반영 (2026-09-15) — 14명 중 13명 2026Q2 13F 수집 (138 filings / 13,008 holdings / 1,817 price tickers, 가격 2026-09-14까지). 명단 교정: Klarman·Einhorn·Pabrai CIK 수정, Greenblatt 제외, Ackman은 `extra_ciks`로 Pershing Square Inc. 합산. 수집 버그 수정: Berkshire information table 누락, NEW HOLDINGS 정정이 원본을 가림, NaN 가격 저장, CINS 코드(Chubb·Accenture·Linde 등 외국 소재 미국 상장사 130종목) 미매핑(매핑률 87.3% → 93.3%). 티커 변경 5건 매핑 갱신(BK→BNY 등). Buffett과 비교할 `SingleManagerClone(Druckenmiller)`를 기본 백테스트에 추가하고, 복제 전략이 같은 티커의 주식·옵션 행을 덮어쓰던 버그를 수정(합산, 풋 제외)

- [x] 백테스트 최적화 (2026-09-20) — 벤치마크 NAV 갱신·집계형 lookahead 규칙·NewBuyOnly `min_positions` 수정 후 79개 설정 탐색(`scripts/sweep_backtests.py`, DB 사본). Calmar 기준 1위 ConsensusTopK(3,10)을 비롯한 계열별 최적값을 기본 스위트에 반영. 보고서 `docs/backtest-optimization-2026-09.md`. `thirteen-f targets` 명령과 SPA **Plan** 탭(비교표 → 권장 전략 → 지금의 목표 비중·매수/매도 목록, `targets.json`) 추가

- [x] 2026Q3 반영·규칙 보완·재스윕 (2026-11-17) — 13명의 2026Q3 13F 수집 (151 filings / 14,441 holdings / 1,864 price tickers, 가격 2026-11-16까지). 규칙 보완: 매니저 자신의 회사 지분 제외(`config/scoring.toml [affiliated_holdings]`), 2분기 이상 뒤처진 13F 제외, 발행사 대표 클래스 유지, 백테스트 시작일을 첫 13F 공개일로, SPY의 최대 낙폭·Sharpe 저장·표시, 그때그때의 목표를 쌓는 `target_log`(`thirteen-f record-targets`). 79개 설정 재스윕과 판정은 `docs/backtest-resweep-2026-11.md` — ConsensusTopK(3,10)은 Calmar 1위지만 이웃 설정보다 유독 높은 봉우리로 판정했고, 같은 날 기본 스위트의 ConsensusTopK를 기준을 통과한 (3,15)로 바꿨다

**unit 303 passed · integration 3 passed + 1 skipped** (2026-11-17) (collect e2e는 로컬 VCR 카세트를 `RECORD_VCR=1`로 녹화해야 실행). (Frontend SPA는 단위 테스트 X — `thirteen-f serve` 후 브라우저 navigate 검증; LLM은 httpx mock + structured JSON schema 검증; Quarto는 사용자 CLI 설치 후 검증)

**CI**: GitHub Actions — `ruff check src tests scripts` + unit 테스트 (Python 3.12·3.14, `.github/workflows/ci.yml`). integration은 네트워크·VCR 때문에 제외.

## Backtest Snapshot (2024-05-13 ~ 2026-11-16, cost_bps=10, 2026-11-17 실행)

기본 8전략의 최신 run이다. 구간은 첫 13F 공개일(2024-05-13)부터 가격 마지막 날(2026-11-16)까지 631영업일이고, SPY도 같은 구간의 값이다. 파라미터는 2026-09 탐색(`docs/backtest-optimization-2026-09.md`)에서 고른 값이고 두 가지만 다르다. ConsensusTopK는 2026-11 재스윕 판정에 따라 (3,10)에서 (3,15)로 바꿨고, MultiManager는 13F를 그만 낸 Burry를 뺐다.

> 2026-09-20 스냅샷(2024-01-02 ~ 2026-09-14, ConsensusTopK(3,10) CAGR 29.93% 등)은 엔진이 다시 산 종목에 보유하지 않은 기간의 수익을 붙이던 버그(2026-10-31 수정)가 들어간 값이라 이 표로 바꿨다. 옛 표는 git 이력에, 그때의 탐색은 `docs/backtest-optimization-2026-09.md`에 남아 있다.

| 전략 | CAGR | MDD | Sharpe | Calmar | SPY 대비 CAGR |
|---|--:|--:|--:|--:|--:|
| SingleManagerClone(Buffett) | 17.08% | 20.50% | 1.06 | 0.83 | +0.69%p |
| SingleManagerClone(Druckenmiller) | 25.33% | 26.12% | 1.05 | 0.97 | +8.94%p |
| ConsensusTopK(3, 15) | 23.31% | 16.60% | 1.33 | 1.40 | +6.91%p |
| ScoreTopK(40) | 20.76% | 19.02% | 1.22 | 1.09 | +4.36%p |
| ConvictionFollow(3) | 21.10% | 18.39% | 1.24 | 1.15 | +4.71%p |
| NewBuyOnly(2, 15) | 3.86% | 31.79% | 0.28 | 0.12 | −12.53%p |
| Ensemble(ConsensusTopK(3,10) 0.5 / ConsensusTopK(2,15) 0.5) — Calmar 1위 | 21.34% | 14.93% | 1.25 | 1.43 | +4.95%p |
| MultiManager(Dalio·Druckenmiller·Tepper, 20) | 16.93% | 25.56% | 0.74 | 0.66 | +0.53%p |
| SPY (벤치마크) | 16.39% | 18.76% | 1.02 | 0.87 | – |

2026-11 재스윕(`docs/backtest-resweep-2026-11.md`, 79개 설정)에서 그때의 기본값 ConsensusTopK(3,10)은 Calmar 1위(같은 구간 CAGR 25.29%, MDD 14.83%, Calmar 1.71)였지만 이웃 설정(0.96~1.40)보다 유독 높아, 고원이 아니라 봉우리(과적합 신호)로 판정했다. 그래서 2026-11-17에 기본값을 같은 계열에서 기준을 통과한 (3,15)로 바꿨다. Ensemble은 재스윕에서 평가한 조합 그대로라 절반이 여전히 (3,10)이다. Calmar가 1.43으로 (3,15)의 1.40보다 조금 높아, Plan 화면의 권장 표시(최신 run 중 Calmar 1위)는 지금 Ensemble에 붙는다. 79개 설정의 중앙값은 CAGR 15.94%로 SPY보다 낮다. 표의 수치를 기대 수익으로 읽지 않는다.

### ⚠️ 해석 주의사항

1. **이전 스냅샷의 `SingleManagerClone(Buffett)` CAGR 0%는 데이터 한계가 아니라 수집 버그였다**
   Berkshire 제출물의 information table 파일명(`56757.xml` 같은 숫자 이름)을 찾지 못해 보유내역이 전부 빠졌고, 2025Q1은 NEW HOLDINGS 정정(4종목)이 원본(110건)을 가렸다. 2026-09에 수정했다. 같은 때 외국 소재 미국 상장사(Chubb·Accenture·Linde 등 CINS 코드 130종목)가 매핑되지 않던 버그를 고치고 매니저 명단(Klarman·Einhorn·Pabrai CIK, Greenblatt 제외, Ackman 법인 변경)을 바로잡아, 2026-05 스냅샷과 대부분의 전략 수치가 달라졌다.

2. **`NewBuyOnly`는 추천하지 않는다** — 2명 이상 신규매수 후보가 분기당 1~8종목뿐이라 NVDA 100%(2025-07), AER 100%(2026-04) 같은 단일 종목 분기가 있고, 성과가 종목 두세 개에 달려 있다(지금 CAGR 3.86%·MDD 31.79%, 재스윕 12칸의 Calmar가 모두 SPY 아래). 화면 비교용으로만 남겼다. 편도 10bp 거래비용 가정은 어느 전략이든 단순하고 slippage·세금·차입 제한 미반영.

3. **백테스트는 첫 13F 공개일(2024-05-13)부터 계산한다**
   SPY 가격은 2024-01-02부터 있지만 첫 13F(2024Q1)가 05-13에 공개돼 그 전까지는 모든 전략이 현금이다. 그 구간을 넣으면 전략의 CAGR만 낮아지고 SPY는 그대로라 비교가 어긋나므로(그때의 기본값 ConsensusTopK(3,10) 기준 21.8% 대 SPY 18.3% ↔ 25.3% 대 16.4%), 2026-11-17부터 `backtest`의 시작일 기본값을 첫 공개일로 두었다 (`--start`로 바꿀 수 있다). 약 2년 반짜리 short-cycle 검증이지 long-cycle 검증이 아니다. 파라미터는 이 표본 안에서 고른 값이라 실제 기대 성과는 표보다 낮게 봐야 한다.

4. **Buffett vs Druckenmiller 복제** — 두 복제 모두 첫 13F가 보이는 2024-05-15부터 투자한다. Druckenmiller 복제(2026-11-16까지 누적 +76%)는 Natera(비중 13~18%)·Insmed·Teva 같은 소수 고확신 종목이 성과를 주도했고, 2025-04 관세 충격 때 하루 −7.7%·+12.9%로 변동도 크다. 복제는 콜옵션을 기초자산 명목금액의 롱 노출로 계산하고(분기별 비중 2.6~16.4%) 풋은 제외하므로, 레버리지·프리미엄이 있는 실제 포지션과 다르다. Duquesne이 금액을 천 달러 단위로 보고한 필링은 collect 단계에서 ×1000 보정된다 (제출물 안의 상대 비중만 쓰는 복제 수익률은 보정 전에도 영향이 없었다).

5. **매니저 구성** — Burry(Scion)는 2025Q3 이후 13F가 없어 최근 분기 컨센서스에서 빠진다. Ackman의 2026Q2는 Pershing Square Inc. 통합 보고라 HHH +900만 주, PSUS 신규처럼 법인이 직접 보유하던 지분이 합쳐져 보이는 변화가 섞여 있다(실제 매매 아님). 2026-11-17부터 ① 매니저 자신의 회사·관계사 지분(Ackman의 Pershing Square Inc·PSUS, Icahn의 IEP — `config/scoring.toml [affiliated_holdings]`)은 점수 계산에서 빼고, ② 가장 최근 분기보다 2분기 이상 뒤처진 13F는 복제·ConvictionFollow·MultiManager에서 쓰지 않으며(Burry의 2025Q3 포트폴리오가 목표에 남아 있었다), ③ 기본 MultiManager는 Dalio·Druckenmiller·Tepper 3명이다.

6. **Lookahead bias 차단은 검증됨** (Spec §7.4)
   5개 전략 × 미래 filing 노출 6 케이스 단위 테스트로 확인. `filings.filed_at <= as_of_date` 가드는 모든 전략 SQL에 강제됨. 매니저 전원의 집계(총점·컨센서스)를 쓰는 전략은 그 분기 13F가 모두 제출된 뒤에만 그 분기를 쓴다 (2026-09 수정 전에는 첫 제출자 기준이라 최대 11일 앞섰다).

7. **집계 전략의 종목 단위** — 컨센서스 상위 종목에 GOOG·GOOGL이 따로 들어가 Alphabet이 두 자리를 차지하고 SPY 같은 ETF도 종목으로 집계되던 문제를, 2026-10-31에 집계 전략(ConsensusTopK·ScoreTopK·NewBuyOnly·ConvictionFollow·MultiManager)의 ETF 제외·발행사(CUSIP 앞 6자리) 합산으로 고쳤다. 복제 전략은 거장 보유 그대로다. 2026-09 탐색 보고서(`docs/backtest-optimization-2026-09.md` §5·§6)의 수치는 이 변경 전 기준이다. 2026-11-17부터 ConsensusTopK·ScoreTopK·NewBuyOnly는 발행사의 대표 클래스를 한번 정하면 바꾸지 않는다 — 분기마다 점수가 높은 클래스를 골라 2024Q1~2026Q3에 GOOG↔GOOGL이 5번 바뀌었고, 그때마다 같은 회사를 팔고 다시 샀다.

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
| `thirteen-f check-filings` | 1 | done (DB에 없는 13F-HR 원본 목록 — 있으면 exit 3, 없으면 0, 확인 실패 2. `scripts/check_and_update.ps1`이 매일 확인해 갱신) |
| `thirteen-f analyze [--threshold FLOAT]` | 2 | done |
| `thirteen-f backtest [--strategy NAME / --all] [--start --end --cost-bps]` | 3 | done (기본 8개: 7종 전략 + Druckenmiller 복제) |
| `thirteen-f targets --strategy NAME [--as-of DATE]` | 3 | done (전략이 지금 지시하는 목표 비중 — 분기마다 매매 목록 확인) |
| `thirteen-f export [--out DIR]` | 5 | done (DuckDB → JSON dump for SPA, `targets.json` 포함) |
| `thirteen-f serve [--host --port --reload]` | 5 | done (FastAPI 정적 SPA on :8765) |
| `thirteen-f report [--quarter Q / --latest] [--open]` | 4 | done (Quarto CLI 필요) |
| `thirteen-f update [--skip-collect / --skip-backtest / --skip-export / --skip-report]` | all | done |

## Tech Stack

**Backend**: Python ≥ 3.11 / uv / httpx / lxml / duckdb / pyyaml / typer / yfinance / rich / tenacity / pydantic v2 / fastapi + uvicorn (Phase 5) / jupyter·plotly (Quarto 전용 `report` extra)
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

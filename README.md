# 13F Portfolio Tracker

미국 투자 거장 15명의 SEC 13F-HR 공시를 EDGAR에서 직접 수집·분석·점수화·백테스트하는 개인용 Python 도구.

## What it does

- **수집**: SEC EDGAR에서 분기별 13F-HR 공시 직접 파싱 (httpx + lxml)
- **분석**: 분기 간 변화·conviction·continuity·consensus 4 시그널 + 가중 종합 점수
- **백테스트**: 6 전략 (SingleManagerClone, ConsensusTopK, ScoreTopK, ConvictionFollow, NewBuyOnly, Ensemble) + Lookahead-free 검증
- **시각화**: Streamlit 5 페이지 대시보드 (Overview / Manager / Signals / Backtest / Compare)
- **리포트**: Quarto 6 챕터 단일 HTML (선택: Gemini LLM 분기 헤드라인 요약 + Top 10 시그널 해석)

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
# .env 편집:
#   SEC_USER_AGENT="Your Name email@domain.com"   (필수)
#   GOOGLE_API_KEY="..."                          (선택, LLM 요약/해석 활성화)
#   GEMINI_THINKING="true"                        (선택, 기본 true)

# 3) DuckDB 11 테이블 초기화
uv run python scripts/init_db.py

# 4) (선택) Quarto CLI 설치 — 분기 HTML 리포트용
#   Windows:  winget install RStudio.Quarto
#   macOS:    brew install --cask quarto
#   미설치 시 dashboard / backtest 는 정상, report 만 안내 후 종료
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
- [x] Phase 4 — Streamlit 5 페이지 + Quarto 6 챕터 + dashboard/report/update CLI
- [x] Phase 4+ — Gemini LLM 통합 (분기 헤드라인 요약 + Top 10 시그널 해석, thinking on/off 토글)

119 unit tests passed. (Phase 4 UI는 단위 테스트 X — Streamlit 부팅 health=200 자동 검증, Quarto 렌더는 사용자 환경 CLI 설치 후 수동 검증; LLM은 httpx mock + 실 Gemini 호출 end-to-end 검증)

## Phase 3 Backtest Snapshot (2024-01-02 ~ 2026-05-20, cost_bps=10)

| 전략 | CAGR | MDD | Sharpe |
|---|--:|--:|--:|
| SingleManagerClone(Buffett) | 0.00% | 0.00% | 0.00 |
| ConsensusTopK(3, 20) | 14.87% | 21.30% | 0.87 |
| ScoreTopK(20) | 24.46% | 17.40% | 1.37 |
| ConvictionFollow(10) | 16.10% | 19.06% | 1.00 |
| NewBuyOnly(2, 15) | 39.74% | 28.14% | 1.35 |
| Ensemble(Buffett 0.4 / ScoreTopK 0.4 / ConsensusTopK 0.2) | 19.41% | 17.79% | 1.16 |

### ⚠️ 해석 주의사항

1. **`SingleManagerClone(Buffett)` CAGR 0%는 코드 버그가 아니라 데이터 한계**
   Buffett(BRK)의 10개 filing 중 9개가 Confidential Treatment로 information table XML이 비어 있고, 36건이 든 1개는 정정본 supersede로 가려져 가용 holdings가 거의 없음. → SEC EDGAR 본문 자체의 한계이며 다른 거장 라벨로 같은 전략을 돌리면 정상 작동.

2. **`NewBuyOnly` CAGR 39.74% 는 과대 노출 가능성**
   17개월 짧은 표본에서 small-cap 신규매수 consensus rotation 효과가 부풀려졌을 수 있음. 편도 10bp 거래비용 가정도 단순하고 slippage·세금·차입 제한 미반영. → 더 긴 기간 데이터가 쌓이면 재검증 필요.

3. **백테스트 가용 시작일은 2024-01-02** (SPY 가격 데이터 시작점)
   `--start 2015-01-01` 같은 더 이른 날짜를 줘도 엔진은 SPY 영업일 기준으로 자동 절삭함. 따라서 현재까지의 결과는 17개월 short-cycle 검증이지 long-cycle 검증 아님.

4. **Lookahead bias 차단은 검증됨** (Spec §7.4)
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
| `thirteen-f backtest [--strategy NAME / --all] [--start --end --cost-bps]` | 3 | done |
| `thirteen-f dashboard` | 4 | done (Streamlit 5 pages on :8501) |
| `thirteen-f report [--quarter Q / --latest] [--open]` | 4 | done (Quarto CLI 필요) |
| `thirteen-f update [--skip-collect / --skip-backtest / --skip-report]` | all | done |

## Tech Stack

Python ≥ 3.11 / uv / httpx / lxml / duckdb / polars / pyyaml / typer / yfinance / rich / tenacity / streamlit + plotly + Quarto (Phase 4) / Gemini API (raw httpx, optional)

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

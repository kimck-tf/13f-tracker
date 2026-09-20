# 백테스트 알고리즘 최적화·선정 (2026-09)

기간 2024-05-13 ~ 2026-09-14(첫 13F 공개일부터 약 2년 4개월, 분기 신호 10번), 편도 거래비용 10bp, 벤치마크 SPY(CAGR 19.05%).
8개 전략 계열의 파라미터 73개 설정 + 앙상블 6개를 DB 사본에서 돌려 비교했다. 원자료는 `data/sweep/sweep_results.csv`(git 제외), 실행은 `scripts/sweep_backtests.py`.

## 결론

| 순위 | 설정 | CAGR | MDD | Calmar | Sharpe | SPY 대비 CAGR | 평균 보유 |
|--:|---|--:|--:|--:|--:|--:|--:|
| **1** | **ConsensusTopK(min_holders=3, top_k=10)** — 3명 이상이 보유한 종목 중 종합점수 상위 10개 동일가중 | **35.3%** | **15.9%** | **2.22** | 1.69 | +16.3%p | 10 |
| 2 | Ensemble: ConsensusTopK(3,10) 50% + ConsensusTopK(2,15) 50% | 33.3% | 15.8% | 2.11 | 1.71 | +14.3%p | 16 |
| 3 | Ensemble: ConsensusTopK(3,10) 60% + MultiManager(macro 4명, top 20) 40% | 36.2% | 19.1% | 1.90 | 1.74 | +17.1%p | 26 |

- 1위는 전 구간·전반·후반 모두에서 SPY를 이겼고(10분기 중 7분기 초과), 이웃 파라미터(2~4명 × 5~15종목)의 Calmar도 1.5~2.1이라 특정 값 하나에 맞춘 결과는 아니다. 다만 10종목 동일가중이라 집중도가 높다.
- 2위는 같은 신호를 15~16종목으로 넓힌 것으로, 수익률 2%p를 내주고 분기 회전율과 종목 집중을 낮춘다. **실제로 따라 하기에는 2위를 권한다.**
- 현행 기본 설정 8개 중 이 기간에 SPY를 의미 있게 이긴 것은 Druckenmiller 복제(42.6%, MDD 26.2%)와 ConsensusTopK(3,20)(22.5%)뿐이다. ScoreTopK(20)·ConvictionFollow(10)·MultiManager(Buffett·Ackman·Tepper)·Ensemble(기본)은 SPY와 비슷하거나 낮았다.
- 표본이 10분기라 어떤 선정도 통계적 확신은 낮다. "이 기간에서 가장 좋았고 구조적으로 설명되는 설정"으로 읽는다.

## 1. 방법

- **기간**: 2024-05-13(첫 13F 공개일)부터. 그 전(2024-01-02~)은 모든 전략이 현금이라 CAGR만 낮추므로 뺐다. README의 스냅샷은 2024-01-02 시작이라 수치가 다르다.
- **평가 지표**: 전 구간 CAGR·MDD·Calmar(CAGR÷MDD)·Sharpe·SPY 대비 초과 CAGR·분기 승률·평균 보유 종목 수. 같은 일별 NAV를 2025-08-14에서 잘라 **전반(H1, 315영업일)·후반(H2, 271영업일)** 지표도 냈다 — 재실행 없이 구간만 자른 것이라 후반 첫날의 리밸런스 비용은 없다.
- **선정 규칙**(사용자 확정): Calmar 1순위, CAGR·MDD 병기. 후보 조건은 ① 평균 보유 8종목 이상 ② 이웃 파라미터(한 축만 한 칸 다른 설정)의 Calmar가 무너지지 않을 것 ③ 후반 구간에서도 SPY를 이길 것.
- **탐색 격자** (73개): ScoreTopK top_k {5,10,15,20,30,40} · ConsensusTopK min_holders {2,3,4} × top_k {5,10,15,20,30} · NewBuyOnly min_holders {2,3} × top_k {5,10,15} × min_positions {1,5} · ConvictionFollow top_k {3,5,10,15,20} · MultiManager 매니저 집합 5종(현행 3명 / value 6명 / activist 4명 / macro 4명 / 14명 전체) × top_k {10,15,20,30} · SingleManagerClone 14명 · Ensemble(현행). 2차로 1위를 핵심으로 한 앙상블 6개.
- **실행**: `uv run python scripts/sweep_backtests.py` → `--only e2_ --append`. 설정당 약 9초.

## 2. 탐색 전에 고친 것

| 문제 | 수정 | 영향 |
|---|---|---|
| 엔진이 전략의 첫 매수 전에는 벤치마크 NAV를 갱신하지 않아 전략마다 SPY CAGR이 달랐다(15.56% vs 16.29%) | 벤치마크를 매일 갱신 (`engine.py`) | 모든 전략의 SPY 기준이 같아졌다(19.05%) |
| ScoreTopK·ConsensusTopK·NewBuyOnly가 분기의 **첫 제출자**가 제출한 날부터 매니저 전원 집계를 썼다 (1~11일 lookahead, 2025Q3: Burry 11-03 vs 나머지 11-12~14) | 그 분기 13F-HR 원본이 **모두** 제출된 날부터 쓴다 (`strategy.latest_public_period`) | 같은 구간 CAGR이 설정에 따라 −2.9 ~ +4.1%p 움직였고 방향은 일정하지 않았다 (아래 표) |
| NewBuyOnly가 후보 1~8종목에 몰려 NVDA 100%(2025-07), AER 100%(2026-04) 분기가 있었다 | `min_positions` 추가 (후보가 그보다 적으면 현금) | MDD는 그대로(31.8%)고 현금 비중만 늘어 개선 효과 없음 — §3.4 |

수정 전 코드로 같은 구간을 돌린 비교 (CAGR, 수정 전 → 후): ScoreTopK(20) 19.2 → 20.8% · ScoreTopK(40) 23.4 → 23.1% · ConsensusTopK(2,15) 27.6 → 29.0% · ConsensusTopK(3,10) 36.0 → 35.3% · ConsensusTopK(3,20) 25.4 → 22.5% · NewBuyOnly(2,15) 42.9 → 47.0%.

## 3. 결과

### 3.1 전 구간 Calmar 상위 15 (평균 보유 8종목 이상)

| # | 설정 | CAGR | MDD | Calmar | Sharpe | SPY 대비 | 보유 | H1 CAGR/MDD | H2 CAGR/MDD | 이웃 Calmar 평균 |
|--:|---|--:|--:|--:|--:|--:|--:|---|---|--:|
| 1 | ConsensusTopK(3,10) | 35.3% | 15.9% | 2.22 | 1.69 | +16.3%p | 10 | 33.1% / 15.9% | 26.8% / 12.0% | 1.60 |
| 2 | Ensemble ConsensusTopK(3,10)·(2,15) 50/50 | 33.3% | 15.8% | 2.11 | 1.71 | +14.3%p | 16 | 29.4% / 15.8% | 28.6% / 13.1% | – |
| 3 | Ensemble ConsensusTopK(3,10) 60 + MultiManager(macro4,20) 40 | 36.2% | 19.1% | 1.90 | 1.74 | +17.1%p | 26 | 30.8% / 19.1% | 37.0% / 7.8% | – |
| 4 | Ensemble ConsensusTopK(3,10) 60 + MultiManager(value6,30) 40 | 29.0% | 15.3% | 1.89 | 1.69 | +9.9%p | 35 | 28.9% / 15.3% | 24.0% / 9.1% | – |
| 5 | ConsensusTopK(2,15) | 29.0% | 15.6% | 1.86 | 1.56 | +10.0%p | 15 | 26.4% / 15.6% | 24.8% / 14.2% | 1.58 |
| 6 | Ensemble ConsensusTopK(3,10) 60 + Druckenmiller 복제 40 | 35.6% | 20.0% | 1.78 | 1.70 | +16.5%p | 70 | 31.5% / 20.0% | 37.0% / 10.7% | – |
| 7 | ConsensusTopK(2,10) | 27.4% | 15.7% | 1.75 | 1.43 | +8.4%p | 10 | 21.1% / 15.7% | 33.8% / 13.3% | 2.05 |
| 8 | Ensemble ConsensusTopK(3,10) 50 + ConvictionFollow(3) 50 | 30.1% | 17.4% | 1.73 | 1.61 | +11.1%p | 36 | 25.8% / 17.4% | 34.5% / 10.8% | – |
| 9 | MultiManager(macro4, 20) | 39.1% | 23.8% | 1.65 | 1.44 | +20.0%p | 20 | 24.3% / 23.8% | 57.7% / 11.8% | 1.43 |
| 10 | Ensemble 3등분: ConsensusTopK(3,10)·MultiManager(macro4,20)·ConvictionFollow(3) | 31.3% | 19.1% | 1.63 | 1.63 | +12.2%p | 46 | 27.1% / 19.1% | 35.6% / 7.3% | – |
| 11 | SingleManagerClone(Druckenmiller) | 42.6% | 26.2% | 1.63 | 1.60 | +23.5%p | 63 | 29.8% / 26.2% | 53.4% / 11.6% | – |
| 12 | ConsensusTopK(4,10) | 30.5% | 20.0% | 1.53 | 1.56 | +11.5%p | 10 | 24.9% / 20.0% | 34.8% / 12.5% | 1.60 |
| 13 | ConsensusTopK(3,15) | 27.5% | 18.1% | 1.52 | 1.48 | +8.4%p | 15 | 31.2% / 18.1% | 20.9% / 12.5% | 1.64 |
| 14 | ConsensusTopK(2,20) | 24.7% | 16.8% | 1.47 | 1.45 | +5.7%p | 20 | 27.7% / 16.8% | 19.6% / 12.1% | 1.38 |
| 15 | MultiManager(macro4, 30) | 33.3% | 22.7% | 1.47 | 1.32 | +14.3%p | 30 | 22.8% / 22.7% | 46.1% / 17.4% | 1.65 |

SPY: 전 구간 19.05%, H1 20.12%, H2 18.07%. 후반(H2)은 대부분 설정의 MDD가 5~13%로 낮은 구간이라 H2 Calmar는 전 구간보다 높게 나오며, 후반 비교는 CAGR과 MDD로 보는 편이 낫다.

### 3.2 계열별 최적 설정과 현행 기본값

| 계열 | 최적 설정 | CAGR | MDD | Calmar | 현행 기본값 | CAGR | MDD | Calmar |
|---|---|--:|--:|--:|---|--:|--:|--:|
| ConsensusTopK | (3, 10) | 35.3% | 15.9% | 2.22 | (3, 20) | 22.5% | 18.0% | 1.25 |
| ScoreTopK | top 40 | 23.1% | 18.9% | 1.22 | top 20 | 20.8% | 23.4% | 0.89 |
| ConvictionFollow | top 3 (34종목) | 25.6% | 18.4% | 1.39 | top 10 (101종목) | 18.0% | 19.1% | 0.95 |
| MultiManager | macro 4명(Burry·Dalio·Druckenmiller·Tepper), top 20 | 39.1% | 23.8% | 1.65 | Buffett·Ackman·Tepper, top 15 | 16.8% | 14.5% | 1.16 |
| SingleManagerClone | Druckenmiller | 42.6% | 26.2% | 1.63 | Buffett | 18.9% | 20.5% | 0.92 |
| NewBuyOnly | (2, 15, min 1) — 평균 5.7종목이라 후보 제외 | 47.0% | 31.8% | 1.48 | 같음 | | | |
| Ensemble | ConsensusTopK(3,10)·(2,15) 50/50 | 33.3% | 15.8% | 2.11 | Buffett 0.4 / ScoreTopK 0.4 / ConsensusTopK(3,20) 0.2 | 20.0% | 20.5% | 0.98 |

읽는 법:
- **ConsensusTopK가 ScoreTopK를 모든 top_k에서 이긴다.** 같은 종합점수로 줄을 세워도 "3명 이상 보유" 조건이 종목 수를 줄이는 것 이상으로 성과를 갈랐다. 컨센서스 후보(3명 이상)는 분기당 38~51종목이라 top 10은 그중 상위 5분의 1이다.
- ConvictionFollow는 매니저별 확신 상위 종목 수를 줄일수록(3개) 낫다. 10개 이상이면 100종목 넘게 들어 지수와 비슷해진다.
- MultiManager는 매니저 집합이 결과를 정한다. macro 4명 조합의 성과는 Druckenmiller·Tepper 보유 종목이 후반(H2 57.7%)에 크게 오른 데 기댄 것이고, value 6명·전체 14명·activist 4명 조합은 SPY와 같거나 낮았다.
- SingleManagerClone 14명 중 이 기간 SPY 대비 초과수익은 Druckenmiller(+23.5%p)·Tepper(+6.5%p)·Klarman(+0.9%p)·LiLu(+0.8%p)뿐이고, Ackman·Loeb·Akre·Pabrai·Icahn·Einhorn 복제는 −7~−18%p였다.

### 3.3 2차: 앙상블

1위 ConsensusTopK(3,10)을 핵심(50~60%)으로 두고 성격이 다른 설정을 섞었다. 어떤 조합도 1위의 Calmar를 넘지 못했지만, ConsensusTopK(2,15)와 섞은 것은 Calmar 2.11로 근접하면서 종목 수를 16개로 늘리고 분기당 새 종목 수를 3.5 → 6.0개로 분산했다. macro MultiManager를 섞으면 CAGR은 오르고(36.2%) MDD가 3%p 커진다. value MultiManager를 섞으면 MDD가 가장 낮고(15.3%) CAGR은 29.0%로 내려간다.

### 3.4 제외하거나 주의할 설정

- **SingleManagerClone(Burry)** — Calmar 1.81이지만 평균 7.5종목이고, Scion이 2025Q3 이후 13F를 내지 않아 2025-11부터는 같은 포트폴리오가 동결된 채 계산됐다. 앞으로 쓸 수 없는 전략이다.
- **ConsensusTopK(2,5)** — Calmar 2.07(CAGR 41.4%)이지만 5종목이라 제외. (3,5)·(4,5)도 같은 이유.
- **NewBuyOnly** — 2명 이상 신규매수 후보가 분기당 1~8종목(2025Q1·2025Q4는 1종목)이라 결과가 한두 종목의 운이다. `min_positions=5`를 주면 현금인 날이 36%가 되고 MDD는 그대로다. min_holders=3은 후보가 거의 없어 현금 75% 이상. 첫 분기(2024Q1)는 직전 분기가 없어 보유 전부가 "신규매수"로 잡혀 사실상 top 15 컨센서스였다. 신호로 쓰려면 후보 풀을 넓히는 정의 변경(예: 비중 확대 포함)이 먼저다.

## 4. 선정 근거

**ConsensusTopK(3,10)**
- 전 구간 Calmar 1위(2.22), H1 2위(2.08), H2에서도 SPY 대비 +8.7%p. 10분기 중 7분기에 SPY를 이겼고 가장 큰 초과는 2025Q3(+23.8% vs +8.2%).
- 이웃 설정 (2,10) 1.75 · (4,10) 1.53 · (3,5) 1.60 · (3,15) 1.52 — 2~4명 × 5~15종목 영역 전체가 1.5 이상이라 봉우리가 아니라 고원이다.
- 보유 예 (2026-07-01): AAPL·AMZN·BN·BRK-B·COF·GOOG·GOOGL·QSR·SPY·UBER 각 10%. 분기당 새 종목 2~5개(평균 3.5).

**Ensemble ConsensusTopK(3,10) 50% + (2,15) 50%** — 같은 신호를 두 굵기로 겹친 것이라 별개 전략이라기보다 "10종목 8% + 나머지 3%" 가중이다. Calmar 2.11, Sharpe 1.71, 16종목. 집중도가 부담스러우면 이쪽.

**Ensemble ConsensusTopK(3,10) 60% + MultiManager(macro4, 20) 40%** — CAGR 36.2%·Sharpe 1.74로 가장 높지만 macro 조합의 후반 쏠림(H1 Calmar 1.02 → H2 4.90)을 그대로 물려받는다. 공격적 선택.

## 5. 한계와 주의

- **표본 10분기.** 전반·후반이 각각 5분기라 "후반에서도 이긴다"는 검증의 힘이 약하다. 파라미터 격자에서 고른 값이므로 실제 기대 성과는 표의 값보다 낮게 봐야 한다.
- **2024~2026은 대형 성장주·AI 강세장**이었다. 컨센서스 상위 10종목은 AMZN·GOOG·META·MSFT·NVDA 같은 대형주가 대부분이라, 이 결과는 "거장들이 함께 보유한 대형주가 지수를 이겼다"는 사실에 크게 기댄다.
- **GOOG·GOOGL이 따로 집계**되어 Alphabet이 사실상 20%다. **SPY(ETF)도 종목으로 들어간다** (Dalio 등 보유). 같은 회사의 복수 클래스를 합치고 ETF를 빼는 규칙은 아직 없다 — §6.
- **비용은 편도 10bp 고정**이고 slippage·세금·차입 제약은 없다. 상장폐지·인수 종목은 마지막 가격으로 수익률 0 처리된다.
- **Burry 동결** (§3.4)처럼 13F를 그만 내는 매니저는 포트폴리오가 멈춘 채 계산된다. 컨센서스 계열은 분모(보유자 수)만 줄어 영향이 작다.
- Baupost·Duquesne의 천 달러 단위 보고는 동일가중·주식 수 기반 전략에 영향이 없다 (금액 가중 MultiManager는 이번 탐색에서 쓰지 않았다).

## 6. 다음 단계 (제안)

1. 기본 스위트(`runner.default_suite`)에 1위 설정을 넣고 현행 ConsensusTopK(3,20)을 대체할지 결정. SPA Backtest 화면은 type당 최신 run 하나만 보여 주므로 type당 1개를 유지한다.
2. 알고리즘 개선 후보 (탐색에 넣지 않은 정의 변경): 같은 회사 복수 클래스(GOOG/GOOGL, BRK-A/B) 합산, ETF(`cusip_ticker_map.is_etf`) 제외, 컨센서스 가중을 동일가중 대신 보유자 수·확신도 가중으로. 각각 결과를 바꿀 수 있어 같은 절차로 다시 재야 한다.
3. 분기마다 `sweep_backtests.py`를 다시 돌려 고원이 유지되는지 확인한다. 1위가 이웃보다 크게 앞서기 시작하면 과적합 신호로 본다.

## 부록: 재현·운용

```bash
uv run python scripts/sweep_backtests.py                 # 1차 73개 → data/sweep/sweep_results.csv
uv run python scripts/sweep_backtests.py --only e2_ --append   # 2차 앙상블 6개

uv run thirteen-f targets --strategy ConsensusTopK       # 지금의 목표 비중 (매 분기 매매 목록)
uv run thirteen-f targets --strategy ConsensusTopK --as-of 2026-05-20   # 과거 시점 기준
```

`targets`는 백테스트와 같은 `get_target_positions`를 호출하므로 lookahead 규칙도 같다 — 그 분기 13F가 모두 제출된 뒤(2·5·8·11월 중순)에 목록이 바뀌고, 그 사이에는 바뀌지 않는다.

CSV 컬럼: `full_*`(전 구간), `h1_*`(2024-05-13~2025-08-14), `h2_*`(2025-08-15~2026-09-14) 각각 `cagr, mdd, sharpe, calmar, bench_cagr, alpha_cagr, avg_positions, min_positions, invested_frac, days`. run 곡선·보유 내역은 `data/sweep/13f.sweep.duckdb`의 `backtest_*` 테이블(run_id는 CSV에).

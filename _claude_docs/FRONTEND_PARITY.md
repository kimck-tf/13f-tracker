# Frontend ↔ Backend Computation Parity

Phase 5 SPA는 데이터의 1차 출처를 명확히 분리한다. 백엔드 exporter는 **사실 데이터(facts)**만 dump하고, 프론트엔드는 그 위에서 **파생/표시 계산(derived/display)**을 수행한다.

이 매트릭스는 각 데이터 항목이 어디서 계산되는지와 검증 방법을 정리한다. 새 페이지를 만들거나 데이터 의문이 생기면 이 표부터 확인.

| 데이터 | 계산 위치 | 검증 방법 |
|---|---|---|
| `QUARTERS` / `Q_LABELS` | Backend (`exporter.export_quarters`) — filings.period_of_report 정렬 + Q-label 생성 | 단일 SSOT, frontend는 read-only |
| `STOCKS[].px[i]` (분기말 close) | Backend (`exporter.export_stocks`) — prices 테이블 분기말 이하 가장 가까운 영업일 | unit test: `test_export_stocks_uses_sector_and_quarter_end_close` |
| `STOCKS[].pxWeekly` | Frontend (`hf-data.js:buildWeeklyPrices`) — quarterly → 8-step interpolation + sin noise | 시각화 전용. 실거래 계산 금지 (분기말 px만 truth) |
| `STOCKS[].s` (sector) | Backend (`cusip_ticker_map.sector` via supplement_sector.py) | `scripts/supplement_sector.py`로 1회 backfill 필수 |
| `MANAGERS[].avatar` | Backend (`exporter._avatar_from_name`) — full name 첫 2글자 | `test_avatar_from_name` |
| `MANAGERS[].color` | Backend (config/managers.yaml → managers.color) — style별 팔레트 | yaml 직접 수정 |
| `HOLDINGS[mgrId][ticker][i]` (백만주) | Backend (`exporter.export_holdings`) — holdings JOIN cusip_ticker_map | `test_export_holdings_splits_mapped_and_unmapped` |
| `HOLDINGS_UNMAPPED` | Backend — mapping 실패 cusip 격리 | 같은 테스트 |
| `classifyAction(prev, curr)` | Frontend (`hf-data.js`) — NEW/ADD/HOLD/CUT/EXIT 분류 | Python의 `signals_quarterly.change_type`과 동일 의미. 별도 export 없음 |
| `managerPortfolio(mgrId, qIdx)` | Frontend (`hf-data.js`) — HOLDINGS × STOCKS.px 곱 + 비중 계산 | 검증 시 sum(weight) ≈ 1.0 확인 |
| `tickerHolders(ticker, qIdx)` | Frontend — HOLDINGS에서 derive | crowdedness/spotlight 계산 입력 |
| `quarterActivity(qIdx)` | Frontend — 모든 매니저 × 종목 action 집계 | spotlight 추출 입력 |
| `spotlight(qIdx)` | Frontend — quarterActivity 최대 abs(deltaValue) | UI 강조용 |
| `BACKTESTS[]` (equity/dd/qrets/holdingsLog/metrics) | Backend (`exporter.export_backtest`) — 분기말 resample + backtest_holdings | `test_export_backtest_writes_runs_with_holdings_and_metrics` |
| `runStrategy(...)` (실시간 backtest in browser) | Frontend (`hf-data.js`) — STOCKS.px 기반 시뮬 (mock-era 잔존, 디자인 prototype 용도) | **실거래 의사결정에 사용 금지**. backend의 `thirteen-f backtest`만 신뢰. Frontend strategy는 BuilderScreen에서 빠른 비교 UI 용도. |
| daily close series (per ticker) | Backend (`exporter.export_prices_split`) — prices/{TICKER}.json | StockScreen에서 `fetchDailyPx(ticker)` lazy 호출. unit test: `test_export_prices_split_per_ticker` |
| `LLM_SUMMARY` (분기별 headline/top_signals) | Backend (`exporter.export_llm_summary` — Chunk D 작성 예정) | 사전 캐시. /api/ask는 실시간 |
| `/api/ask` 응답 | Backend (Chunk D `summary.chat_reply`) — Gemini chat with structured cards | 호출 시점마다 새로 생성 |

## 원칙

1. **사실(facts)**: backend가 SSOT. 프론트는 fetch만, 파싱·표시만.
2. **표시 파생(display derive)**: 분류·소계·랭킹·강조 등 — 프론트에서 계산. 백엔드 추가 dump 불필요.
3. **불일치 발견 시**: backend가 정답. 프론트 helper를 backend SQL과 맞추는 방향으로 수정.
4. **`runStrategy` 같은 prototype 코드**: backtest UI를 mock으로 보여주는 용도. 실 백테스트는 `thirteen-f backtest --all` + `BACKTESTS[]` JSON 사용.

## 변경 추적

- 신규 데이터 항목 추가 시 이 표에 한 줄 추가
- 계산 위치를 backend → frontend로 또는 그 반대로 옮길 때 같은 표 갱신
- 변경 PR에는 이 파일 diff 포함

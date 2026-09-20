# Architecture

CLAUDE.md `## Architecture`를 보충한다. 파일 목록은 `git ls-files`로 확인하고, 이 문서에는 여러 파일을 읽어야 알 수 있는 흐름과 계약만 적는다.

## 단계별 입출력

| 명령 | 진입점 | 읽기 | 쓰기 | 다시 실행하면 |
|---|---|---|---|---|
| `collect` | `collect/pipeline.py:run_collect` | `config/managers.yaml`, EDGAR, OpenFIGI, yfinance(+Stooq) | `managers`, `filings`, `holdings`, `cusip_ticker_map`, `prices`, `data/logs/failed_tickers.jsonl` | upsert로 갱신 (중복 행 없음) |
| `analyze` | `analyze/pipeline.py:run_analyze` | `filings`, `holdings`, `managers`, `cusip_ticker_map`, `config/scoring.toml` | `signals_quarterly`, `consensus_quarterly`, `total_scores` | 세 테이블을 DELETE 후 전체 재계산 |
| `backtest` | `backtest/runner.py:run_suite`(`--all`), `backtest/engine.py:run_backtest` | 분석 테이블, `filings`, `holdings`, `prices` | `backtest_runs`, `backtest_curves`, `backtest_metrics`, `backtest_holdings` | 새 `run_id`(uuid)로 누적, 이전 run은 남음 |
| `export` | `web/cli.py:do_export` → `web/exporter.py` | 전체 (read-only 연결) | `src/thirteen_f/web/data/` | 파일 덮어쓰기 |
| `serve` | `web/cli.py:do_serve` → `web/server.py:app` | `web/static/`, `web/data/`, `/api/ask` 요청마다 DuckDB read-only | — | — |
| `report` | `cli.py:report` → `quarto render reports/quarto/` | DuckDB (`reports/quarto/_common.py`) | `reports/output/<분기 또는 _latest>/` | 덮어쓰기 |
| `update` | `cli.py:update` | — | 위 단계를 `sys.executable -m thirteen_f.cli <단계>` subprocess로 차례로 실행 (serve 제외) | — |

## collect (Phase 1)

1. `resolve_cik.resolve_missing_ciks` — `managers.yaml`에서 CIK가 빈 매니저를 SEC `company_tickers.json`으로 채우고, 실행할 때마다 yaml을 `yaml.safe_dump`로 다시 쓴다. 문자열이 아닌 CIK(따옴표 없는 8진수형 값)가 있으면 파일을 쓰기 전에 `ValueError`로 멈춘다.
2. 매니저별로 대표 `cik`와 `extra_ciks` 각각의 submissions JSON → 13F 필링 목록 → `period_of_report >= --start`만 남김 (필링은 대표 `cik`로 저장하고 EDGAR 원문은 실제 제출자 CIK 경로에서 받음. 대표 CIK가 보고한 분기의 추가 CIK 제출분은 쓰지 않고 이전 실행분은 `remove_filing`) → 13F-HR/A는 표지(`primary_doc.xml`)의 `amendmentType`이 NEW HOLDINGS면 적재하지 않음(이전 실행분은 `loader.remove_filing`으로 삭제) → filing index에서 `primary_doc.xml`이 아닌 XML을 information table로 선택(파일명이 `56757.xml`처럼 제각각이라서) → `parser.parse_information_table` → `loader.upsert_holdings`(같은 PK로 분할 보고된 행을 SUM한 뒤 accession 단위로 delete+insert).
3. 매니저마다 `loader.mark_supersedes(cik)`로 정정본을 표시한다.
4. `cusip_mapper.fill_missing` — `cusip_ticker_map`에 없는 CUSIP만 OpenFIGI로 조회해 캐시한다 (매핑 실패도 `ticker=NULL` 행으로 캐시되어 다시 조회하지 않는다). 첫 글자가 알파벳인 CINS 코드는 `ID_CINS`, 나머지는 `ID_CUSIP`으로 조회한다.
5. `price_loader.download_prices` — ticker마다 yfinance, 비어 있으면 Stooq. 둘 다 실패하면 실패 로그(jsonl)에 추가한다.

EDGAR 요청은 `edgar_client.py`가 초당 8건으로 제한하고(SEC 한도 초당 10건) `httpx.HTTPError`에 tenacity로 최대 4회 시도한다.

## analyze (Phase 2)

`analyze/pipeline.py` 호출 순서 (정확한 공식은 Spec §6.1):

1. `diff.compute_signals_quarterly` — 매니저×종목×분기 `change_type` ∈ `new`/`increase`/`hold`/`decrease`/`exit`. 주식 수 변화율이 ±`--threshold`(기본 0.05) 이내면 `hold`.
2. `conviction.update_conviction_scores` — 해당 매니저의 최대 비중 종목 대비 비중 (`min(1, weight / top_weight)`).
3. `continuity.update_continuity_scores` — 최근 `WINDOW=4`분기 안에서 new/increase/hold가 끊기지 않고 이어진 분기 수 ÷ 4.
4. `consensus.compute_consensus` — 분기×종목의 보유 거장 수, 신규매수 거장 수.
5. `score.compute_total_scores` — consensus(보유 거장 수 ÷ 전체 거장 수), conviction 평균, continuity 평균, cloning_quality(`managers.cloning_score_weight` 평균)를 `scoring.toml` 가중치로 합산한다. `exit` 행은 제외.

`concentration.py`(HHI)와 `cloning_quality.py`는 이 파이프라인에서 호출되지 않는다. HHI는 `_legacy_dashboard`만 쓰고 cloning_quality 계산은 `score.py` SQL에 인라인돼 있으므로, 점수 공식은 `score.py`에서 바꾼다.

## backtest (Phase 3)

- **Strategy 계약** (`backtest/strategy.py`): `get_target_positions(as_of_date, conn) -> {ticker: weight}`. 비중 합 1.0, `ticker IS NULL` 제외, SQL에 lookahead 가드. `name`에 파라미터를 넣는다(예: `ScoreTopK(20)`) — `backtest_runs.strategy_name`과 SPA 매칭 키로 쓰인다.
- **엔진** (`engine.run_backtest`): 벤치마크(SPY) 가격이 있는 날만 영업일로 순회하므로 `--start`/`--end`는 SPY 가격 범위로 잘린다. 매 영업일 전략을 호출해 target이 바뀐 날만 리밸런싱하고 turnover × `cost_bps`(편도)를 차감한다(첫 진입 포함). 그날 가격이 없는 종목은 직전 가격으로 채워 수익률 0으로 둔다. 분기 첫 영업일 비중을 `holdings_log` → `backtest_holdings`에 저장한다.
- **복제 전략의 옵션 처리** (`strategies/single_manager.py`): 최신 제출물의 행을 ticker별로 합산해 금액 비율로 비중을 매긴다. 콜옵션은 기초자산 명목금액의 롱 노출로 포함하고, 풋은 롱 노출이 아니므로 제외한다. 금액 단위가 틀린 제출자(Druckenmiller)도 제출물 안 상대 비중이라 영향이 없다.
- **기본 suite** (`runner.default_suite`, 8개): `SingleManagerClone(Buffett)`, `SingleManagerClone(Druckenmiller)`, `ConsensusTopK(3,10)`, `ScoreTopK(40)`, `ConvictionFollow(3)`, `NewBuyOnly(2,15)`, `Ensemble`(ConsensusTopK(3,10) 0.5 / ConsensusTopK(2,15) 0.5), `MultiManager`(Burry·Dalio·Druckenmiller·Tepper, top 20). 파라미터는 2026-09 탐색(`docs/backtest-optimization-2026-09.md`)의 계열별 최적값이고, `cli.py` registry와 SPA `hf-data.js:STRATEGY_TYPES`의 기본값도 같게 맞춘다. 집계 테이블을 읽는 전략은 분기를 `strategy.latest_public_period`로 고른다(매니저 전원 제출 뒤).
- **전략 이름 해석** (`runner.strategy_by_name`, `backtest --strategy`·`targets --strategy` 공용): `ScoreTopK`, `ConsensusTopK`, `ConvictionFollow`, `NewBuyOnly`, `MultiManager`(파라미터 없는 이름은 `default_suite()`의 같은 type 전략을 쓴다 — 기본값이 suite 한 곳에만 있게), `SingleManagerClone(<label>)`, `MultiManager(<label>,<label>[:top_k])`. `SingleManagerClone`·`Ensemble`은 파라미터 없는 이름으로 못 부르고, `Ensemble`은 `--all`로만 실행된다.
- **`thirteen-f targets`** (`cli.py`): 전략이 지금 지시하는 목표 비중을 출력한다. 백테스트와 같은 `get_target_positions`를 read-only 연결로 호출하므로 lookahead 규칙도 같다 — 분기 13F가 모두 제출된 뒤(2·5·8·11월 중순)에 목록이 바뀐다.

## web (Phase 5)

- **exporter** (`web/exporter.py`, 호출 순서는 `web/cli.py:do_export`): managers → quarters → stocks → prices_split → holdings → backtest → meta. 파일별 형태는 `DATA_FORMATS.md`.
  - `export_holdings`는 분기 `q`마다 `period_of_report = q`이고 `filed_at <= q + 180일`인 유효본만 쓴다. 45일 공시 기한을 넘긴 늦은 제출도 180일까지는 포함한다.
  - `export_backtest`는 DB의 모든 run을 `created_at DESC`로 넣는다.
- **schemas** (`web/schemas.py`): Pydantic 모델은 `QuarterEntry`, `Manager`, `Stock`, `Meta`이고 exporter는 그중 `QuarterEntry`, `Manager`, `Meta`만 쓴다 (stocks는 dict로 직접 생성). holdings·backtest·prices JSON의 형태는 exporter 코드와 `hf-data.js` 사용처가 사실상의 계약이다.
- **server** (`web/server.py`): `GET /api/health`, `POST /api/ask`, `/data`(StaticFiles), `/`(StaticFiles `html=True`). `/` 마운트가 모든 경로를 받으므로 새 `/api/*` 라우트는 파일 끝 `app.mount(...)`보다 위에 정의한다. `/api/ask`는 IP당 분당 10회 제한(프로세스 메모리) → 요청마다 DuckDB read-only 연결 → `llm.summary.chat_reply`.
- **SPA** (`web/static/`): 빌드 단계가 없다. `index.html`이 CDN에서 React 18 UMD와 Babel standalone을 받고 `hf-data.js` → `tweaks-panel.jsx` → `hf-components.jsx` → 화면별 `.jsx` → `hf-app.jsx`(hash router, 기본 `#/home`) 순서로 로드한다. 파일끼리는 각 파일 끝 `Object.assign(window, {...})`로 노출한 전역을 쓴다.
  - `hf-data.js:bootstrapFromJson`이 JSON 8개를 `Promise.all`로 받아 전역(`META`, `QUARTERS`, `STOCKS`, `MANAGERS`, `HOLDINGS`, `HOLDINGS_UNMAPPED`, `BACKTESTS`, `LLM_SUMMARY`)을 채운다. 일봉은 `fetchDailyPx(ticker)`로 필요할 때만 받는다.
  - Backtest 화면(`hf-backtest.jsx:matchBackendRun`)은 `BACKTESTS`에서 `name`이 전략 type으로 시작하는 첫 run(=최신)을 쓴다. `SingleManagerClone`은 매니저 전체 이름의 마지막 단어가 `(…)` 안에 있어야 매칭된다. 못 찾으면 `hf-data.js:runStrategy` 브라우저 시뮬레이션(SIM 배지, KPI 비교 제외)으로 대신한다.

## llm (Phase 4+ / 5)

- `gemini.py:generate` — Gemini REST를 httpx로 직접 호출한다. `response_schema`를 주면 JSON 응답을 강제하고, `enable_thinking=False`면 `thinkingConfig.thinkingBudget=0`.
- `prompts.py` — `quarterly_headline_prompt`, `signal_explain_prompt`, `chat_prompt` + `CHAT_SCHEMA`. `chat_prompt`는 질문 1900자 절단, `###` 제거, "이전 지시 무시" 요청 거부 문구로 prompt injection을 막는다.
- `summary.py` — DB 조회 후 호출: `headline_summary`(max_output_tokens 4096), `explain_top_signals`(8192), `chat_reply`(8192). `chat_reply`의 컨텍스트는 `web/ask_context.py:build_context`가 질문에서 ticker(알려진 ticker 집합과 교집합, stopword 제외)와 매니저(`MANAGER_KEYWORDS`)를 뽑아 만든다.
- 호출하는 곳: Quarto `index.qmd`(headline), `03_signals.qmd`(explain), `/api/ask`(chat).

## report / legacy

- `cli.py:report` — Quarto는 렌더 중 cwd를 `reports/quarto/`로 바꾸므로 CLI가 `.env`를 직접 읽어 환경변수로 넘기고 `DUCKDB_PATH`를 절대경로로 바꾼다. 분기는 `-P` 인자 대신 `THIRTEEN_F_QUARTER` 환경변수로 전달하고, qmd 셀은 `_common.py:resolve_quarter`로 읽는다. `04_backtest.qmd`는 누적된 run 중 전략별 최신 run만 표·차트로 비교한다.
- `_legacy_dashboard/` — Streamlit이 의존성에서 빠져 페이지는 실행되지 않는다. `charts.py`(plotly)만 Quarto `01_overview.qmd`·`04_backtest.qmd`가 import한다.

## 설계 문서 지도

- `docs/superpowers/specs/2026-05-20-13f-tracker-design.md` — Phase 0~4 설계 기록. §4.2 스키마(`init_db.py`와 동일), §5 수집, §6 시그널, §7 백테스트, §10 Phase별 DoD. 구현 후 달라진 점(SPA 전환·`dashboard` 제거·MultiManager·Stooq 구현·`analysis.toml` 미사용)은 문서 상단 "현행화 노트"에 있고, 본문의 해당 절(§3.2, §7.2, §8 등)은 설계 당시 그대로다.
- `docs/superpowers/plans/2026-05-21-13f-tracker.md` — Phase 0~4 TDD step. Chunk 1~5 = Phase 0~4, Task N.x = Phase N.
- `docs/superpowers/plans/2026-05-22-13f-frontend-migration.md` — Phase 5. Chunk A 백엔드 기반 · B 정적 서빙 · C 프론트 데이터 연결 · D MultiManager + Ask LLM · E 정리.
- `참고/` — 구현 전 사전 조사 노트 (`PLAN.md`, `edgar_notes.md`, `schema.md`).
- `handoff/` (git 미추적) — 구현 전에 받은 디자인 핸드오프 번들. 디자인 토큰·화면 명세·인터랙션만 참고한다. 그 안의 구조 권고(Next.js·TanStack, "`hf-data.js`가 알고리즘 정답")는 실제 구현과 다르며, 계산의 정답은 backend다 (`FRONTEND_PARITY.md`).

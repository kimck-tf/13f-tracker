# Troubleshooting & Known Issues

증상으로 찾는다. 각 항목에 원인과 조치를 함께 적고, 해결된 항목은 지운다.

## 테스트·도구

- **`test_collect_buffett_one_quarter`가 skip됨** — VCR 카세트 `tests/fixtures/cassettes/buffett_2024q1.yaml`은 로컬 전용(`.gitignore`)이라 저장소에 없고, 없으면 skip된다. 녹화하려면 `RECORD_VCR=1 uv run pytest tests/integration/test_collect_e2e.py`(실제 SEC 네트워크 필요). 일상 회귀는 `uv run pytest tests/unit`.
- **`uv sync`(또는 의존성 변경 후 `uv run`)가 `failed to remove file …\.venv\Scripts\thirteen-f.exe` (os error 32)로 실패** — 실행 중인 `thirteen-f serve` 프로세스가 exe를 잡고 있다. 서버를 끈 뒤(Ctrl+C, 또는 작업 관리자에서 `thirteen-f.exe` 종료) 다시 실행한다. 당장 명령만 돌려야 하면 `uv run --no-sync …`. 2026-09-15 이전의 `tests/integration/test_serve.py`는 Windows에서 서버 프로세스 트리를 남기는 버그가 있었다 (`taskkill /T`로 수정).
- **`ruff check`·`mypy` 위반이 대량으로 나옴** — 기존 기준선이다 (2026-09-15: `ruff check src tests` 106건, `mypy src/thirteen_f` 43건). mypy 43건은 `_legacy_dashboard` 20건(streamlit 미설치, stub 없음)과 나머지 23건 — `fetchone()[0]`의 Optional 인덱싱 13건, yaml·lxml·pandas·yfinance stub 없음 6건, `cli.py`·`web/exporter.py` 타입 불일치 4건이다. 수정한 파일의 위반 수가 늘지 않았는지만 확인한다.
- **`ValueError: SEC_USER_AGENT 미설정`** — `load_settings()`를 거치는 collect·analyze·backtest·export·`/api/*`가 모두 요구한다. `.env`는 cwd에서 읽으므로 저장소 루트에서 실행했는지도 확인한다.
- **`IOException: IO Error: Cannot open file "…13f.duckdb"`** — 다른 프로세스가 DB를 쓰기 모드로 열고 있으면 read-only로도 열 수 없다 (collect·analyze·backtest 실행 중에 export·report·`/api/ask`·노트북·DB 뷰어를 함께 쓸 때). 한쪽이 끝난 뒤 실행한다.

## 수집·데이터

- **매니저의 13F가 수집되지 않거나 다른 운용사 데이터가 들어감** — `config/managers.yaml`의 CIK가 다른 엔터티를 가리키는 경우다. 확인·교체 절차는 WORKFLOWS.md "매니저 CIK 변경·추가·제외". 2026-09-15에 바로잡은 사례: Klarman `0001061165`(Lone Pine Capital) → Baupost `0001061768`, Einhorn `0001385613`(Greenlight Capital Re, 재보험사) → DME Capital Management `0001489933`(보유 1위 Green Brick Partners로 Greenlight 포트폴리오임을 확인), Pabrai `0001173334`(개인) → Dalal Street `0001549575`. Ackman은 2026Q2부터 13F-NT만 내고 보유내역은 Pershing Square Inc. `0002026053`이 보고해 `extra_ciks`로 합산한다. Greenblatt(Gotham `0001510387`, 1,791종목)은 편입 시 3명 이상 보유 종목이 39 → 186개로 늘어 신호가 흐려져 명단에서 뺐다. Burry(Scion)는 2025Q3 이후 13F가 없다.
- **Ackman 2026Q2에 HHH +900만 주, PSUS 신규 같은 변화가 보임** — 2026Q2부터 Pershing Square Inc.가 펀드 보유분과 법인 자체 보유분을 합쳐 보고해서 생긴 표시상 변화다(실제 매매 아님). 이전 분기에는 대표 CIK(Pershing Square Capital Management)의 펀드 보유분만 쓴다 (`extra_ciks` 규칙, DATA_FORMATS.md `config/`).
- **Klarman·Druckenmiller의 금액이 1000배 작음** — Baupost Group과 Duquesne Family Office는 information table `value`를 천 달러 단위로 보고한다 (둘 다 2024Q1~2026Q2 전 분기, 표지 합계도 동일). Li Lu 2024Q1도 같다. `normalize_value`는 제출일(2023-01-03 경계)로만 판단해 보정되지 않는다. 점수·백테스트·SPA는 상대 비중·주식 수를 써서 영향이 없고, 금액을 그대로 쓰는 곳(LLM 컨텍스트, `value_change_usd` 기반 표시)만 틀린다. 점검: 분기말 종가 대비 `value_usd / shares` 중앙값이 0.001이면 이 경우다 (미수정).
- **`thirteen-f update` 후 수집 범위와 소요 시간이 크게 늘어남** — `update`는 `collect`를 `--start` 없이 호출해 기본값 `2011Q1`(Spec §1.3 설계 범위)부터 수집한다. 현재 DB는 `--start 2024Q1`로 수집한 상태(2026-09-15 기준 filings 138건, 2024Q1~2026Q2)다. 범위를 유지하려면 `collect --start`를 따로 실행하고 `update --skip-collect`.
- **collect가 `ValueError: managers.yaml <label>: cik가 문자열이 아닌 …`으로 멈춤** — 따옴표 없이 0~7 숫자로만 쓴 CIK를 YAML이 8진수 int로 읽었다. 해당 CIK를 따옴표로 감싼다 (이유는 DATA_FORMATS.md `config/`).
- **새 매니저 CIK가 자동으로 안 채워짐** — `company_tickers.json`에 ticker가 없는 13F 전용 filer다 (예: Nygren = Harris Associates L P). `managers.yaml`에 따옴표로 감싸 직접 입력한다 (`cik: '0000813917'`).
- **`managers.yaml`에 단 주석이 사라짐** — collect가 실행할 때마다 파일을 `yaml.safe_dump`로 다시 쓰기 때문이다. 매니저 설명은 `notes` 필드에 적는다.
- **OpenFIGI 매핑률 93.3% (보유 CUSIP 기준, 2026-09)** — 남은 미매핑은 워런트·사모·외국 거래소 전용 증권이다. 실패 CUSIP은 `ticker=NULL`로 캐시되고 SPA에서는 `holdings_unmapped.json`으로 분리된다. 2026-09-15 이전의 87.3%에는 첫 글자가 알파벳인 CINS 코드(Chubb·Accenture·Linde·Medtronic 등 외국 소재 미국 상장사 130종목)를 `ID_CUSIP`으로 조회해 전부 실패한 버그가 섞여 있었다. 그 전에 수집한 DB라면 `ticker IS NULL AND regexp_matches(cusip, '^[A-Za-z]')` 행을 `cusip_mapper._openfigi_batch`로 다시 조회해 티커가 나온 것만 `upsert_mapping`한다 (캐시된 실패는 `fill_missing`이 재조회하지 않음).
- **가격 누락 15 ticker** — AKRO, AMED, CADE, CDTX, CIVI, CMA, CVAC, CYBR, DNB, HES, PCH, WBA (상장폐지·합병) + FLYX-WS, NPWR-WS, OXY-WS (워런트). 백테스트는 해당 비중의 수익률을 0으로 처리한다. 실패 목록은 `data/logs/failed_tickers*.jsonl`.
- **보유 중인 종목의 가격이 어느 날짜에서 끊김** — 두 경우가 있다. ① 티커 변경: `cusip_ticker_map`은 캐시 미스만 OpenFIGI로 조회하므로(`fill_missing`) 옛 티커가 남아 가격 다운로드가 실패한다 (2026-09 확인: BK→BNY, EQR→VMRK, LC→HAPN, SATS→ECHO, VSCO→VSXY). 해당 CUSIP을 `cusip_mapper._openfigi_batch`로 다시 조회해 **새 티커가 있고 기존과 다를 때만** `upsert_mapping`으로 갱신한 뒤, 새 티커 가격을 `download_prices`로 받는다 (결과가 비었다고 기존 티커를 NULL로 덮으면 과거 보유 기록이 끊긴다). ② 상장폐지·인수 (예: AMWD, EA, GTLS, LBRDA·LBRDK): 조치할 것이 없다 — 백테스트는 마지막 가격을 유지해 수익률 0으로 처리한다. 점검 쿼리: 최근 분기 유효 holdings의 ticker 중 `MAX(prices.date)`가 SPY 마지막 날짜보다 10일 이상 이른 것.
- **`No info table XML for <label>/<accession>` 경고** — 표지(`primary_doc.xml`)만 있고 information table이 없는 제출물이다 (정상). 2026-09-15 이전에는 파일명 탐지 버그로 Berkshire 전 분기와 Burry 2024년 제출 3건이 이 경고와 함께 누락됐다 — 그 시기의 DB 백업·백테스트 수치(`SingleManagerClone(Buffett)` CAGR 0% 등)는 이 버그의 결과다.
- **`Skip NEW HOLDINGS amendment` 로그** — 추가 공개분만 담은 13F-HR/A라 적재하지 않은 것이다 (정상, Spec §5.2). 원본이 그 분기의 유효본으로 남는다.
- **`config/analysis.toml`을 고쳐도 결과가 그대로** — 이 파일을 읽는 코드가 없다. 실제 조정 위치는 DATA_FORMATS.md `config/`.
- **SPA 섹터가 전부 "Other", treemap 색이 단조로움** — `cusip_ticker_map.sector`가 비어 있다. `uv run python scripts/supplement_sector.py` 후 `export`.

## 백테스트

- **`backtest --all` 결과가 `CAGR=nan%`** — `prices`에 NaN 가격 행이 있다. yfinance가 아직 확정되지 않은 마지막 거래일을 NaN으로 주는 경우가 있고(2026-09 수집 때 413종목의 2026-09-14 행), 엔진은 `None`만 걸러서 NaN이 NAV 전체로 번진다. `_upsert_prices`가 NaN 종가 행을 저장하지 않도록 고쳤으므로, 그 전에 수집한 DB라면 `SELECT COUNT(*) FROM prices WHERE isnan(close) OR isnan(adj_close)`로 확인하고 해당 행을 지운 뒤 그 종목들의 최근 가격을 다시 받는다. NaN으로 계산된 backtest run은 `backtest_holdings`·`backtest_curves`·`backtest_metrics`·`backtest_runs` 순으로 지운다.
- **시작일을 더 이르게 줘도 2024-01-02부터 계산됨** — 엔진은 SPY 가격이 있는 영업일만 순회한다. 현재 SPY 가격이 2024-01-02~2026-09-14라 `--start` 기본값 `2013-01-01`도 잘린다. 첫 13F(2024Q1)가 2024-05-13에 공개돼 그 전까지는 모든 전략이 현금이고, 약 32개월 표본이라 장기 검증은 데이터가 쌓인 뒤 다시 해야 한다.
- **`NewBuyOnly` CAGR이 높은데 MDD도 30%를 넘음** — 2명 이상 신규매수 후보가 분기당 1~8종목뿐이라 NVDA 100%(2025-07), AER 100%(2026-04)처럼 한두 종목에 몰린 분기의 결과다. `min_positions`(후보가 그보다 적으면 현금)를 붙여도 MDD는 그대로고 현금 비중만 늘어난다 (`docs/backtest-optimization-2026-09.md`). 첫 분기(2024Q1)는 직전 분기가 없어 보유 전부가 "신규매수"로 잡히는 점도 있다. 비용은 편도 10bp 단순 가정(slippage·세금 미반영)이므로 어느 전략이든 실거래 재현성으로 해석하지 않는다.
- **`backtest_holdings`가 비어 있는 run** — Phase 5 이전에 실행된 run이다. `uv run thirteen-f backtest --all`을 다시 실행한다.
- **같은 전략 run이 여러 개 쌓임** — run마다 새 uuid `run_id`로 누적되고 삭제 로직이 없다 (2026-09-15 기준 전략별 1~4건). `backtest.json`에 모든 run이 들어가고 Backtest 화면은 type별 최신 run을 쓴다.
- **`--strategy Ensemble` → `Unknown strategy`** — 단일 실행 registry에 없다. `--all`로 실행한다.
- **MultiManager의 매니저별 기준 분기가 서로 다름** — 의도된 동작이다. 매니저마다 `as_of_date` 기준 최신 13F-HR 1건을 쓰므로 A는 Q3, B는 Q4일 수 있다 (`test_multi_manager_per_manager_different_periods`). `weighting="byvalue"`는 서로 다른 분기의 value를 합산하는 stale-period bias가 있어 기본값은 `equal`이다.

## 웹·LLM

- **SPA가 빈 화면** — `index.html`이 React·Babel(unpkg)과 폰트(Google Fonts, jsdelivr)를 CDN에서 받으므로 인터넷 연결이 필요하다. JSON이 없으면 ErrorScreen에 누락 파일명과 HTTP 상태가 표시된다 → `uv run thirteen-f export`.
- **Backtest 화면에 `SIM` 배지** — 해당 전략의 backend run을 `BACKTESTS`에서 찾지 못해 `hf-data.js:runStrategy` 브라우저 시뮬레이션으로 대신한 것이다 (KPI 비교에서 제외). `backtest --all` → `export` 후 새로고침.
- **`llm_summary.json` 요청이 404** — 이 파일을 만드는 exporter가 아직 없다 (`FRONTEND_PARITY.md`의 `LLM_SUMMARY` 행). frontend가 `{}`로 대체하므로 동작에는 영향이 없다.
- **`/api/ask`가 429 또는 503** — 429는 IP당 분당 10회 제한이다. 카운터가 프로세스 메모리 dict라 `uvicorn --workers >1`이면 워커별로 따로 세므로 단일 워커를 전제한다. 503은 `GOOGLE_API_KEY` 미설정.
- **Gemini 응답이 중간에 잘림** — thinking 모델(`gemini-3-flash-preview`)은 `max_output_tokens`를 thinking과 응답이 나눠 쓴다. `uv run python scripts/bench_llm.py`로 `finishReason`과 `thoughtsTokenCount`를 확인하고 한도를 올린다 (현재 `gemini.generate` 기본 8192, headline 4096, explain·chat 8192).
- **`thirteen-f report`가 exit 2** — OS에 Quarto CLI가 없다. Windows는 `winget install RStudio.Quarto`.
- **`thirteen-f dashboard` 명령이 없음** — Phase 5에서 제거됐다 (Spec §3.2와 plan `2026-05-21` Chunk 1·5에는 설계 당시 기록으로 남아 있음). `thirteen-f serve`를 쓴다.

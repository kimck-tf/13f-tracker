# Data Formats

## DuckDB

경로는 `DUCKDB_PATH`(기본 `data/13f.duckdb`, cwd 상대). 컬럼 정의의 정답은 `scripts/init_db.py`이고, 여기에는 컬럼 이름만으로는 알 수 없는 의미를 적는다. 데이터를 다룰 때 지킬 규칙(lookahead, 정정본, 단위)은 CLAUDE.md `## Invariants`에 있다.

| 테이블 | PK | 의미 |
|---|---|---|
| `managers` | `cik` | `managers.yaml` upsert 결과. `label`은 전략 파라미터(`SingleManagerClone(<label>)`)와 SPA id(`label` 소문자)로 쓰는 짧은 키, `cloning_score_weight`는 cloning_quality 점수의 원천 |
| `filings` | `accession_no` | `period_of_report` = 보고 분기말, `filed_at` = 공개일(백테스트에서 이날부터 사용 가능). `superseded_by IS NULL` = 해당 (cik, 분기)의 유효본. NEW HOLDINGS 유형 13F-HR/A는 저장하지 않는다 |
| `holdings` | `(accession_no, cusip, title_of_class, put_call)` | `value_usd`는 달러 단위. `put_call = ''`이면 옵션이 아닌 보유 |
| `cusip_ticker_map` | `cusip` | `ticker IS NULL` = OpenFIGI 매핑 실패. `sector`/`industry`는 `scripts/supplement_sector.py` 실행 전엔 `''` |
| `prices` | `(ticker, date)` | 엔진은 `adj_close`, `export_stocks`는 분기말 `close`를 쓴다 |
| `signals_quarterly` | `(cik, cusip, period_of_report)` | `change_type`, `weight_pct`, conviction/continuity 점수 |
| `consensus_quarterly` | `(period_of_report, cusip)` | `holder_count`, `new_buy_count`, `holder_ciks` |
| `total_scores` | `(period_of_report, cusip)` | 4개 성분 점수 + `total_score` |
| `backtest_runs` | `run_id` | uuid hex. `strategy_name` = `Strategy.name`, `params_json`, `cost_bps`, `benchmark` |
| `backtest_curves` | `(run_id, date)` | 일별 `nav`, `benchmark_nav`, `position_count` |
| `backtest_metrics` | `run_id` | total_return, CAGR, Sharpe, Sortino, MDD, Calmar, 분기 승률, 벤치마크 수익률 |
| `backtest_holdings` | `(run_id, rebalance_date, ticker)` | 분기 첫 영업일 목표 비중 |

- `SCHEMA_SQL`의 `CREATE TABLE IF NOT EXISTS`는 이미 있는 테이블에 컬럼을 더하지 않는다. 기존 DB에 컬럼을 추가할 때는 `MIGRATIONS`에 `ALTER TABLE … ADD COLUMN IF NOT EXISTS`를 넣는다.
- `tests/unit/test_init_db.py`가 생성된 테이블 집합을 `EXPECTED_TABLES`와 대조한다.
- `backtest_curves`, `backtest_metrics`, `backtest_holdings`는 `backtest_runs(run_id)`를 외래키로 참조한다 — run을 지울 때는 이 세 테이블부터 지운다.

## JSON export (`src/thirteen_f/web/data/`)

gitignore 대상이며 `uv run thirteen-f export`로 다시 만든다. SPA는 `/data/<파일>`로 받는다.

| 파일 | 만드는 함수 | 형태 | SPA 전역 |
|---|---|---|---|
| `meta.json` | `export_meta` | `Meta` 모델 (`latest_period`, `llm_available` 등) | `META` |
| `quarters.json` | `export_quarters` | `[{key: "2024Q2", label: "Q2'24", date: "2024-06-30"}]` | `QUARTERS`, `Q_LABELS`, `Q_DATES` |
| `quarters_index.json` | `export_quarters` | `{"2024-03-31": 0, …}` | 사용하지 않음 (테스트만 검증) |
| `managers.json` | `export_managers` | `Manager` 모델 (`id` = label 소문자, `avatar` = 이름 이니셜) | `MANAGERS`, `MGR_MAP` |
| `stocks.json` | `export_stocks` | `[{t: ticker, n: 이름, s: sector, i: industry, px: [분기별 close 또는 null]}]` | `STOCKS`, `STOCK_MAP` |
| `holdings.json` | `export_holdings` | `{<manager id>: {<ticker>: [분기별 보유 주식 수(백만 주)]}}` | `HOLDINGS` |
| `holdings_unmapped.json` | `export_holdings` | `{<manager id>: {<cusip>: {name_of_issuer, shares: [...]}}}` | `HOLDINGS_UNMAPPED` (없으면 `{}`) |
| `backtest.json` | `export_backtest` | `[{run_id, name, params, equity, dd, qrets, benchEquity, holdingsLog, metrics}]` — DB의 모든 run | `BACKTESTS` (없으면 `[]`) |
| `prices/<TICKER>.json` | `export_prices_split` | `{date: [...], close: [...]}` 일봉 | `fetchDailyPx(ticker)` |
| `targets.json` | `export_targets` | `{as_of, rule, recommended, strategies: [{name, type, period, public_since, next_rebalance, metrics, positions: [{ticker, weight, prevWeight, action: "buy"\|"keep", holders, holderIds, name, sector, isEtf, lastClose, lastCloseDate}], sells: [...]}]}` — 기본 suite 8전략의 **현재** 목표 비중(백테스트와 같은 `get_target_positions`)과 직전 목록(그 분기 공개 전날 기준) 대비 diff. `recommended`는 최신 run 중 Calmar 1위(평균 보유 8종목 이상) | `TARGETS` (없으면 `null`, Plan 탭이 안내 표시) |
| `llm_summary.json` | 없음 — 만드는 코드가 아직 없다 | — | `LLM_SUMMARY` (`{}`로 대체) |

분기 배열(`px`, 보유 주식 수)의 인덱스는 `quarters.json` 순서와 같다.

## config/

- **`managers.yaml`** — 매니저당 `name`, `label`, `cik`, `fund`, `style`(`value` 6 / `activist` 4 / `macro` 4), `color`, `active_since`, `notes`, `cloning_score_weight`, 선택 `extra_ciks`.
  - **`extra_ciks`** — 운용 법인이 바뀌어 다른 CIK로 13F를 내는 경우의 새 CIK 목록 (예: Ackman의 Pershing Square Inc. `'0002026053'`). collect가 그 제출분을 대표 `cik`로 저장하므로 분기 변화 계산이 끊기지 않는다. 추가 CIK 제출분은 대표 CIK가 13F-HR을 내지 않은 분기에만 쓴다 — Pershing Square Inc.는 2025Q2~2026Q1에도 HHH 한 종목짜리 13F를 같은 날 따로 내서, 정정본 규칙("늦게 제출된 1건만 유효")에 걸려 기존 법인의 전체 포트폴리오를 가렸었다.
  - **CIK는 따옴표로 감싼 10자리 문자열로 쓴다.** PyYAML은 `cik: 0001061165`처럼 따옴표 없이 0~7 숫자로만 된 값을 8진수 int(287349)로 읽고, collect는 이런 값을 만나면 파일을 다시 쓰기 전에 `ValueError`로 멈춘다. 기존 항목 중 따옴표 없는 CIK는 8·9가 섞여 문자열로 읽히므로 `yaml.safe_dump`가 따옴표를 생략한 것이다.
  - collect는 실행할 때마다 이 파일을 `yaml.safe_dump`로 다시 쓴다 — 주석은 지워지고 키 순서는 유지된다. `cik`를 비워 두면 `company_tickers.json`으로 채우는데, 13F 전용 filer는 여기서 찾지 못하므로 직접 입력한다.
- **`scoring.toml`** — `[weights]` consensus / conviction / continuity / cloning_quality, 합 1.0(±0.01).
- **`analysis.toml`** — **읽는 코드가 없다.** 실제로 쓰이는 값은 diff threshold = `analyze --threshold`(기본 0.05), continuity 윈도우 = `analyze/continuity.py:WINDOW`(4), 컨센서스 최소 보유자 수 = 전략 생성자 인자(`ConsensusTopK(min_holders=…)` 등)다.

## 환경변수

`core/config.py:load_settings`가 cwd의 `.env`를 `override=False`로 읽는다 — 같은 이름의 OS 환경변수가 있으면 그 값이 우선한다.

| 변수 | 필수 | 내용 |
|---|---|---|
| `SEC_USER_AGENT` | 필수 | `"Name email@domain.com"`. 비어 있으면 `load_settings()`가 ValueError. SEC는 누락 시 403 |
| `OPENFIGI_API_KEY` | 선택 | 무인증 25 req/min, 인증 250 req/min |
| `STOOQ_API_KEY` | 선택 | `price_loader.py`가 `os.environ`에서 직접 읽는다 (`.env.example`에는 없음). 없으면 Stooq fallback을 건너뜀 |
| `DUCKDB_PATH` | 선택 | 기본 `data/13f.duckdb` |
| `GOOGLE_API_KEY` | 선택 | 없으면 LLM 기능 전체 skip |
| `GOOGLE_MODEL` | 선택 | 기본 `gemini-3-flash-preview` |
| `GEMINI_THINKING` | 선택 | 기본 `true`. `false`면 `thinkingBudget=0` — headline 실측 7.44s → 3.91s, 품질은 미세하게 하락 |
| `THIRTEEN_F_QUARTER` | 자동 | `thirteen-f report`가 Quarto에 넘기는 분기 (`latest` 또는 분기 라벨) |
| `RECORD_VCR` | 테스트 | `1`이면 collect e2e 테스트가 실제 네트워크로 VCR 카세트를 녹화 |

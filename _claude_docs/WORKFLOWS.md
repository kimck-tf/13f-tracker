# Workflows

변경 종류별 절차. 각 절 마지막의 "완료" 줄이 작업이 끝났다고 판단하는 기준이다. 공통 규칙(Phase 승인, TDD, 파일 지정 stage)은 CLAUDE.md `## Workflow Rules`에 있다.

## 새 분기 13F 반영

1. `data/13f.duckdb`를 복사해 백업한 뒤 `uv run thirteen-f collect --start <기존 DB와 같은 시작 분기>` — `update`는 `--start`를 넘기지 않아 기본값 `2011Q1`(Spec §1.3 설계 범위)부터 수집한다. 가격 단계가 전 종목(약 1,650개)을 다시 받으므로 2시간 가까이 걸린다 (2026-09 실측: EDGAR 1분, OpenFIGI 5분, 가격 약 2시간). 실행 중에는 DB가 잠겨 다른 프로세스가 읽을 수 없다.
2. SEC에 13F-HR을 낸 매니저 수와 `filings`의 새 분기 행 수가 같은지, 가격 실패 로그(`Both sources failed`)에 새 종목이 있는지 확인한다. 보유 중인데 가격이 끊긴 종목은 TROUBLESHOOTING.md의 "가격이 어느 날짜에서 끊김" 항목대로 처리한다.
3. 새 ticker가 생겼으면 `uv run python scripts/supplement_sector.py`.
4. `uv run thirteen-f update --skip-collect` — analyze → backtest --all → export → report. Quarto CLI가 없으면 `--skip-report`를 붙인다.

완료: `src/thirteen_f/web/data/quarters.json`에 새 분기가 있고, `serve` 중인 브라우저를 새로고침하면 새 분기가 보인다.

## 백테스트 전략 추가

먼저 읽기: Spec §7.1–7.4, `docs/superpowers/plans/2026-05-21-13f-tracker.md` Chunk 4 (Task 3.x).

1. 실패하는 테스트부터: `tests/unit/backtest/`에 동작 테스트, `test_lookahead_guard.py`에 `test_<strategy>_blocks_future`.
2. `backtest/strategies/<name>.py`에서 `Strategy`를 상속한다.
   - 모든 SQL에 `filings.filed_at <= as_of_date`. `holdings`를 직접 읽으면 `superseded_by IS NULL`, `form_type LIKE '13F-HR%'`도 붙인다 (`single_manager.py`, `multi_manager.py` 참고).
   - `ticker IS NOT NULL`, 비중 합 1.0, 파라미터를 담은 `name`, `params_json` 오버라이드.
3. `runner.default_suite()`에 등록한다. `--strategy`로도 돌리려면 `cli.py` backtest 명령의 registry에도 추가한다.
4. SPA에 보이게 하려면 `web/static/hf-data.js`의 `STRATEGY_TYPES`에 type을 추가한다. `matchBackendRun`이 type으로 시작하는 첫 run을 쓰므로 suite에는 type당 전략을 1개만 둔다 — 같은 type이 둘이면 최신 run 하나만 화면에 나온다. 예외로 `SingleManagerClone`은 매니저 이름의 마지막 단어(`(Buffett)`, `(Druckenmiller)`)로 구분되므로 매니저별로 여러 개 둘 수 있다.

완료: `uv run pytest tests/unit` 통과, `backtest --all` 출력에 새 전략 행이 있고, `export` 후 Backtest 화면에서 SIM 배지 없이 표시된다.

## 시그널·점수 변경

먼저 읽기: Spec §6.1, `docs/superpowers/plans/2026-05-21-13f-tracker.md` Chunk 3 (Task 2.x).

1. `tests/unit/analyze/`에 실패하는 테스트.
2. 계산은 `analyze/<signal>.py`, 호출 순서는 `analyze/pipeline.py`, 가중합은 `analyze/score.py` SQL에서 바꾼다.
3. 점수 성분을 추가·삭제하면 `scoring.toml [weights]`, `ScoreWeights`, `total_scores` 컬럼(→ 아래 스키마 절차)을 함께 바꾸고 가중치 합 1.0을 유지한다.
4. `analyze` → `backtest --all` → `export`를 다시 실행한다 — 점수를 쓰는 전략 결과가 바뀐다.

완료: `uv run pytest tests/unit` 통과, `uv run thirteen-f analyze`가 행 수 통계(`OK: {...}`)를 출력하며 끝난다.

## DuckDB 스키마 변경

1. `scripts/init_db.py`: `SCHEMA_SQL` 수정, 기존 DB용 `MIGRATIONS` 항목 추가, 새 테이블이면 `EXPECTED_TABLES`에도 추가.
2. 쓰는 코드(`collect/loader.py`, `analyze/*`, `backtest/engine.py:_persist_result`)와 읽는 코드(`web/exporter.py`, `backtest/strategies/*`, `llm/summary.py`, `web/ask_context.py`)를 고친다. `_persist_result`처럼 `INSERT INTO <table> VALUES (?, …)` 위치 기반으로 넣는 문장은 컬럼이 늘면 깨진다.
3. `data/13f.duckdb`를 복사해 백업한 뒤 `uv run python scripts/init_db.py`.
4. Spec §4.2의 DDL에도 같은 변경을 반영한다.

완료: `uv run pytest tests/unit` 통과, 실제 DB에서 `DESCRIBE <table>`로 새 컬럼이 보이고, Spec §4.2 DDL과 `SCHEMA_SQL`의 테이블·컬럼·타입이 일치한다 (두 DDL을 DuckDB 메모리 DB에 각각 실행해 `information_schema.columns` 비교).

## 새 데이터를 SPA로 노출

1. `web/exporter.py`에 `export_<name>(conn, out_dir)`, `tests/unit/web/test_exporter.py`에 테스트.
2. 레코드 형태가 고정이면 `web/schemas.py`에 Pydantic 모델을 두고 exporter에서 사용한다.
3. `web/cli.py:do_export`에 호출을 추가한다.
4. `web/static/hf-data.js:bootstrapFromJson`의 `Promise.all`에 `fetchJson("<파일>.json", <fallback>)`을 추가한다. 없으면 안 되는 파일은 fallback을 생략한다 — 누락 시 ErrorScreen에 파일명이 표시된다.
5. `_claude_docs/FRONTEND_PARITY.md`에 계산 위치, `_claude_docs/DATA_FORMATS.md` JSON 표에 형태를 한 줄씩 추가한다.

완료: `uv run pytest tests/unit/web` 통과, `uv run thirteen-f export` 후 브라우저 콘솔 오류 없이 값이 표시된다.

## SPA 수정

1. `src/thirteen_f/web/static/`에서만 수정한다 (`handoff/design/`은 원본 참고용).
2. 새 `.jsx` 파일은 `index.html`에서 그 파일을 쓰는 스크립트보다 앞에 `<script type="text/babel" src="…">`로 넣고, 다른 파일이 쓸 컴포넌트는 파일 끝 `Object.assign(window, {…})`에 추가한다.
3. `uv run thirteen-f serve` → 브라우저에서 해당 화면과 콘솔을 확인한다. frontend 단위 테스트는 없다.

완료: 수정한 화면이 콘솔 오류 없이 렌더링되고 `uv run pytest tests/unit/web` 통과.

## CLI 서브커맨드 추가

1. `src/thirteen_f/cli.py`에 `@app.command()`를 추가하고, 기존 명령들처럼 import는 함수 본문 안에 둔다 — 한 명령을 실행할 때 다른 명령의 의존성(uvicorn, duckdb 등)을 불러오지 않는다.
2. 다른 typer 명령 함수를 Python에서 직접 호출하지 않는다 — 인자 기본값이 `OptionInfo` 객체 그대로 들어가 타입 에러가 난다. 여러 명령을 묶을 때는 `update`처럼 `sys.executable -m thirteen_f.cli <args>` subprocess로 호출한다.
3. `update` 흐름에 넣을 단계면 `run_step([...])`과 `--skip-<name>` 옵션을 함께 추가한다.

완료: `uv run thirteen-f <명령> --help`가 옵션을 보여주고, 새 동작의 테스트가 통과한다.

## LLM 프롬프트·응답 변경

1. 문구와 JSON 스키마는 `llm/prompts.py`, DB 조회와 호출 파라미터는 `llm/summary.py`, `/api/ask` 컨텍스트는 `web/ask_context.py:build_context`에서 바꾼다.
2. thinking ON이면 `max_output_tokens`는 thinking과 응답의 합산 한도다. headline 4096, explain·chat 8192 아래로 줄이지 않는다.
3. Quarto 셀(`index.qmd`, `03_signals.qmd`)은 `enable_thinking=_settings.gemini_thinking`을 계속 넘긴다.
4. `chat_prompt`의 injection 방어(1900자 절단, `###` 제거, 지시 무시 거부 문구)를 유지한다 — `tests/unit/llm/test_chat.py`가 검증한다.

완료: `uv run pytest tests/unit/llm` 통과. `GOOGLE_API_KEY`가 있으면 `uv run python scripts/bench_llm.py` 출력이 `finish=STOP`(잘림 아님)이다.

## 매니저 CIK 변경·추가·제외

1. 제출자가 맞는지 확인한다: `data.sec.gov/submissions/CIK{cik}.json`의 `name`, 최신 13F 표지(`primary_doc.xml`)의 서명자, 보유 상위 종목. fund 이름 부분 일치로 자동 해석된 CIK는 틀리기 쉽다 (2026-09: Klarman → Lone Pine Capital, Einhorn → Greenlight Capital Re였음).
2. `data/13f.duckdb`를 백업한 뒤 `config/managers.yaml`을 고친다 (CIK는 따옴표로 감싼 문자열). 운용 법인이 바뀌어 새 CIK로 제출하면 `cik`는 그대로 두고 `extra_ciks`에 새 CIK를 넣는다.
3. 바꾸거나 뺀 매니저의 옛 CIK 행을 holdings(그 filings의 accession) → filings → managers 순서로 지운다. `managers.cik`가 PK라 yaml만 바꾸면 옛 행이 남아 전체 거장 수(consensus 분모)가 늘어난다.
4. `uv run thirteen-f collect --start <기존 시작 분기>` → `uv run python scripts/supplement_sector.py` → `uv run thirteen-f update --skip-collect`.
5. 매니저 명단이 바뀌었으면 README 명단 표, CLAUDE.md 첫 줄의 인원수, `web/ask_context.py`의 `MANAGER_KEYWORDS`를 맞춘다.

완료: `SELECT COUNT(*) FROM managers`가 yaml의 매니저 수와 같고, 각 매니저의 최신 분기 filings가 SEC 제출 현황과 일치한다.

## 수집 결과 보정 (전체 재수집 대신)

- `scripts/supplement.py` — 슬래시 ticker 정규화 + 누락 ticker 가격 재다운로드용 일회성 스크립트. Nygren 처리 로직이 하드코딩돼 있으므로 실행 전에 코드를 읽고 필요한 부분만 쓴다.
- `scripts/supplement_sector.py` — `cusip_ticker_map.sector/industry`를 yfinance로 채운다.

완료: 보정 대상 행을 다시 조회해 누락이 줄었는지 `data/logs/failed_tickers*.jsonl`과 대조한다.

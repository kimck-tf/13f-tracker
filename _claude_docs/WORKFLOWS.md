# Workflows

변경 종류별 절차. 각 절 마지막의 "완료" 줄이 작업이 끝났다고 판단하는 기준이다. 공통 규칙(Phase 승인, TDD, 파일 지정 stage)은 CLAUDE.md `## Workflow Rules`에 있다.

## 새 분기 13F 반영

0. `uv run thirteen-f check-filings` — DB에 없는 13F-HR 원본이 EDGAR에 있으면 매니저·분기·제출일·accession을 한 줄씩 보여 주고 exit 1, 없으면 `새 13F-HR 없음`과 exit 0, 확인이 실패하면(네트워크·`.env`·DB 잠금) exit 2. collect가 적재하지 않는 것은 세지 않는다 — 정정본(13F-HR/A, 원본과 함께 collect가 처리), DB 최소 분기보다 이른 분기, 대표 CIK도 보고한 분기의 `extra_ciks` 제출분. 매일 자동으로 확인·갱신하려면 아래 "새 공시 자동 확인·갱신".
1. `uv run thirteen-f update --skip-backtest --skip-export --skip-report` — `update`는 시작할 때 `data/backups/`(Google Drive 동기화 폴더)에 DB 사본을 만들어 최근 3개를 남기고, collect는 DB의 최소 분기부터 수집한다 (`--start`로 바꿀 수 있다). 가격 단계는 종목별 마지막 저장일 10일 전부터만 받고, 배당·분할로 수정 종가가 소급 조정되면 그 종목의 저장 이력 전체를 같은 비율로 재스케일한다 (전체 기간을 다시 받는 것은 겹치는 구간이 한 비율로 설명되지 않는 종목뿐 — 데이터 정정이나 저장 이력 안의 단절). `--start`를 DB의 가장 이른 가격보다 앞당기면 그 실행은 전 종목을 새 시작일부터 받는다. 요청은 시작일이 같은 종목을 50개씩 묶어 보내므로 약 1,650종목에 5분 안팎 걸린다 (2026-10-31 100종목 실측 17.4초, 배치 2번. 배치에서 빠진 종목만 종목당 1번씩 다시 받는다. 전체 기간을 받던 2026-09에는 EDGAR 1분, OpenFIGI 5분, 가격 약 2시간). 실행 중에는 DB가 잠겨 다른 프로세스가 읽을 수 없다.
2. SEC에 13F-HR을 낸 매니저 수와 `filings`의 새 분기 행 수가 같은지, 가격 실패 로그(`Both sources failed`)에 새 종목이 있는지 확인한다. 보유 중인데 가격이 끊긴 종목은 TROUBLESHOOTING.md의 "가격이 어느 날짜에서 끊김" 항목대로 처리한다.
3. 새 ticker가 생겼으면 `uv run python scripts/supplement_sector.py`.
4. `uv run thirteen-f update --skip-collect` — analyze → backtest --all → export → report. Quarto CLI가 없으면 `--skip-report`를 붙인다.

완료: `src/thirteen_f/web/data/quarters.json`에 새 분기가 있고, `serve` 중인 브라우저를 새로고침하면 새 분기가 보인다.

## 백테스트 전략 추가

먼저 읽기: Spec §7.1–7.4, `docs/superpowers/plans/2026-05-21-13f-tracker.md` Chunk 4 (Task 3.x).

1. 실패하는 테스트부터: `tests/unit/backtest/`에 동작 테스트, `test_lookahead_guard.py`에 `test_<strategy>_blocks_future`.
2. `backtest/strategies/<name>.py`에서 `Strategy`를 상속한다.
   - 모든 SQL에 `filings.filed_at <= as_of_date`. `holdings`를 직접 읽으면 `superseded_by IS NULL`, `form_type LIKE '13F-HR%'`도 붙인다 (`single_manager.py`, `multi_manager.py` 참고). `total_scores`·`consensus_quarterly`를 읽으면 분기는 `strategy.latest_public_period`로 고른다 (`score_top_k.py` 참고).
   - `ticker IS NOT NULL`, 비중 합 1.0, 파라미터를 담은 `name`, `params_json` 오버라이드.
3. `runner.default_suite()`에 등록한다. `--strategy`로도 돌리려면 `cli.py` backtest 명령의 registry에도 추가한다.
4. Backtest 화면은 `BACKTESTS`의 전략 이름(`name`)별 최신 run을 칩으로 보여 주므로, `backtest --all`에 들어가면 따로 할 일이 없다. 이름이 같으면 최신 run 하나만 나오므로 suite에는 이름이 겹치지 않게 둔다. 칩 툴팁 설명은 `web/static/hf-data.js`의 `STRATEGY_TYPES`(type·name·desc·color)에서 온다.

완료: `uv run pytest tests/unit` 통과, `backtest --all` 출력에 새 전략 행이 있고, `export` 후 Backtest 화면에 새 전략 칩이 보인다.

파라미터 비교는 `uv run python scripts/sweep_backtests.py`로 한다 — DB 사본(`data/sweep/`)에서 돌리므로 본 DB와 SPA 데이터에 run이 쌓이지 않는다. 설정 목록은 스크립트의 `build_configs`, 결과는 `data/sweep/sweep_results.csv`(전 구간·전반·후반 지표).

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

- `scripts/supplement_sector.py` — `cusip_ticker_map.sector/industry`를 yfinance로 채운다.

완료: 보정 대상 행을 다시 조회해 누락이 줄었는지 `data/logs/failed_tickers*.jsonl`과 대조한다.

## 서버 자동 시작

`thirteen-f serve`(http://127.0.0.1:8765)는 장시간 실행이라 `update`에 없다. Windows 로그온 때 자동으로 띄우려면 작업 스케줄러에 등록한다. Smart App Control이 venv 런처를 막아도 뜨도록 `scripts\py.ps1`로 실행한다.

1. 저장소 루트의 PowerShell에서 등록한다. 로그온 트리거를 현재 사용자로 한정해 관리자 창이 아니어도 등록된다.

```powershell
$root = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\py.ps1`" -m thirteen_f.cli serve"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "13f-serve" -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $settings
Start-ScheduledTask -TaskName "13f-serve"
```

2. `curl.exe -s http://127.0.0.1:8765/api/health`가 `{"llm_available": …}`를 돌려주는지 본다.
3. 해제: `Unregister-ScheduledTask -TaskName 13f-serve -Confirm:$false`.

완료: 다시 로그온한 뒤 `/api/health`가 200을 돌려주고, 브라우저 `http://127.0.0.1:8765/#/plan`에 데이터가 보인다.

## 새 공시 자동 확인·갱신

`scripts/check_and_update.ps1`은 `check-filings`가 exit 1(새 13F-HR)일 때만 `update --skip-report` → `scripts/supplement_sector.py` → `export`를 차례로 돌린다. exit 0이면 그대로 끝나고, 확인이 실패하면(exit 2) 갱신하지 않는다. 각 단계는 Smart App Control을 피해 `scripts\py.ps1`로 실행하고, 출력은 `data/logs/check_and_update.log`에 시각과 함께 덧붙인다. 제출 기간(분기말 뒤 45일)에는 매니저가 낼 때마다 그날 갱신되므로 기한 전에는 일부 매니저만 들어간 분기가 화면에 보인다 — 전략은 `latest_public_period` 규칙대로 전원이 제출한 뒤에야 그 분기를 쓴다.

1. 저장소 루트의 PowerShell에서 등록한다. 매일 08:00(한국 시간 아침은 미국 장 마감 뒤라 그날 종가가 확정돼 있다)이고, 그 시각에 PC가 꺼져 있었으면 켜진 뒤 실행한다.

```powershell
$root = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\check_and_update.ps1`""
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "13f-check-filings" -Action $action -Trigger (New-ScheduledTaskTrigger -Daily -At 8am) -Settings $settings
```

2. 한 번 바로 돌려 본다: `Start-ScheduledTask -TaskName 13f-check-filings` → `Get-Content data\logs\check_and_update.log -Tail 20 -Encoding UTF8`. `(Get-ScheduledTaskInfo -TaskName 13f-check-filings).LastTaskResult`가 0이면 새 공시가 없었거나 갱신까지 마친 것이고, 그 밖의 값은 실패한 단계의 exit code다.
3. 해제: `Unregister-ScheduledTask -TaskName 13f-check-filings -Confirm:$false`.

완료: 로그에 그날 날짜의 `> -m thirteen_f.cli check-filings` 줄과 `새 13F-HR 없음`(또는 갱신 단계와 `갱신 완료`)이 있다.

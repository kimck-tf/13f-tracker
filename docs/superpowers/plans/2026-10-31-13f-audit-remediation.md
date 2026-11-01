# 13F Tracker 점검 보완 (Phase 0~3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-10-31 점검에서 찾은 환경 장애·시그널 버그·알고리즘 정의 미결·운영 함정을 네 Phase로 나눠 고치고, 2026Q3 13F(기한 2026-11-16)를 바른 로직으로 반영한 뒤 재스윕까지 마친다.

**Architecture:** 기존 구조(DuckDB 단일 파일을 단계 사이의 유일한 연결점으로 쓰는 collect → analyze → backtest → export → serve 파이프라인)는 그대로 둔다. 변경은 각 단계의 SQL·함수 안에서 끝나고, 프론트엔드는 backend가 내보내는 사실 데이터만 쓰도록 되돌린다(브라우저 시뮬·보간 가격 제거). 새 모듈은 `core/db_tools.py`(DB 파일 유틸), `collect/value_units.py`(단위 보정), `collect/watch.py`(새 공시 감지), `reports/quarto/_charts.py`(Quarto 차트) 네 개뿐이다. 스키마는 바꾸지 않는다.

**Tech Stack:** Python ≥3.11(실행은 uv 전역 고정 3.14.8), uv 0.12, DuckDB, typer, pytest, ruff, React 18 UMD + Babel standalone(빌드 없음), PowerShell(Windows 11 운영 스크립트), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-31-13f-audit-findings.md` (점검 결과·수치·우선순위). 설계 기준은 `docs/superpowers/specs/2026-05-20-13f-tracker-design.md`(§5 수집, §6 시그널, §7 백테스트).

## Global Constraints

- 응답·문서·주석은 한국어, 파일 인코딩 UTF-8 (전역 CLAUDE.md §0).
- **Phase 단위 진행**: 한 Phase를 마치면 멈추고 그 Phase의 DoD를 보고한 뒤 사용자 승인을 받는다 (프로젝트 CLAUDE.md Workflow Rules).
- **TDD**: 실패하는 테스트 → 최소 구현 → `tests/unit` 전체 통과 → 커밋. 커밋 메시지는 기존 로그 형식 `type(scope): 영어 요약` (예: `fix(analyze): …`).
- **stage는 파일을 지정해서** (`git add <path>`). `git add .`·`-A` 금지 — 루트에 `handoff/`, `data/logs/`, `.omc/` 같은 미추적 자료가 있다.
- **`data/13f.duckdb`는 git 밖 유일본**: 테이블 DROP·DELETE·재생성·파일 삭제 전에 사용자 확인 + 복사본. 이 계획에서 본 DB를 고치는 쓰기는 `update`/`collect`/`analyze` CLI와 Task 1.5의 `UPDATE holdings`뿐이며, 모두 Task 1.2의 자동 백업 뒤에 실행된다.
- **frontend는 `src/thirteen_f/web/static/`에서만 수정**. 사실 데이터는 backend exporter가 정답이고 frontend는 표시용 파생 계산만 한다.
- **정적 검사**: 수정한 파일의 ruff·mypy 위반이 수정 전보다 늘지 않게 한다. Task 2.1 뒤에는 `uv run ruff check src tests scripts`가 항상 통과해야 한다.
- **Invariants 유지** (프로젝트 CLAUDE.md): lookahead 차단(`filings.filed_at <= as_of_date`, 집계 테이블은 `latest_public_period`), `superseded_by IS NULL`, value 단위(달러), holdings PK, 가중치 합 1.0, CINS → `ID_CINS`, 스키마 SSOT `scripts/init_db.py`.
- **테스트 실행 명령**: 기본은 `uv run pytest tests/unit -q`. Smart App Control이 `.venv\Scripts\python.exe`를 막아 `uv run`이 `os error 4551`로 실패하면 Task 0.4의 `scripts\py.ps1 -m pytest tests/unit -q`를 쓴다. 아래 "Run:" 줄의 `uv run …`은 모두 이 대체 명령으로 바꿔 읽을 수 있다 (`uv run thirteen-f X` → `scripts\py.ps1 -m thirteen_f.cli X`, `uv run python x.py` → `scripts\py.ps1 x.py`).
- **외부로 나가는 작업은 사용자 확인 후**: `git push`, 작업 스케줄러 등록, Drive 동기화 설정 변경(Task 0.2). `_brain`(`C:\_PYTHON\_brain`)은 읽기 전용 — 미결 목록 갱신은 Phase가 끝난 뒤 사용자가 `/brain`으로 한다.
- 서브에이전트를 띄울 때 `model` 파라미터를 지정하지 않는다.
- 브라우저 확인이 필요한 Task(2.3·2.4·2.7·3.3)는 `uv run thirteen-f serve`를 띄운 뒤 `http://127.0.0.1:8765/#/<route>`를 열어 콘솔 에러가 없는지 본다 (Claude in Chrome의 `read_console_messages`로 확인 가능).

## Review Focus

점검 결과(spec)가 암시하지만 아래 Task의 테스트가 직접 다루지 않던 입력 중, 사용자를 가장 먼저 물 것들. 각 줄의 테스트를 해당 Task의 Step에 넣어 두었다.

1. **holdings가 비어 있는 필링**(information table 누락·파싱 실패로 `filings` 행만 있는 분기) — 그 분기를 "제출"로 보면 보유 전부가 `exit`로 잡힌다. 제출 분기는 holdings가 있는 필링에서만 뽑아야 한다 → Task 1.3 `test_no_rows_after_exit_and_no_exit_for_unparsed_or_missing_filings`.
2. **같은 발행사 접두사(CUSIP 6자리)를 공유하지만 다른 증권인 행**(보통주 + 워런트·우선주) — 발행사 합산이 둘을 한 자리로 합친다. 점수가 높은 클래스 하나만 남는 것이 의도이므로 허용하되 테스트로 동작을 고정한다 → Task 1.6 `test_consensus_top_k_keeps_one_share_class_per_issuer`.
3. **yfinance가 겹치는 구간의 마지막 날을 NaN으로 주는 경우** — 비율을 NaN 날짜로 계산하면 전체 이력이 NaN으로 재스케일된다. 비율은 두 쪽 모두 값이 있는 마지막 날로 계산한다 → Task 1.7 `test_download_prices_rescales_history_after_dividend_or_split`(NaN 마지막 행 포함).
4. **일부 행만 천 달러로 보고된 필링**(관측된 적 없음) — 중앙값 기준이라 과반이 천 달러일 때만 보정한다. 옵션 행은 판정에서 뺀다 → Task 1.5 `test_option_rows_are_ignored_in_detection`.
5. **가격 데이터 자체가 오래된 상태에서의 targets export**(마지막 수집이 두 달 전) — "오늘" 기준으로 stale을 판정하면 전 종목이 stale이 된다. 기준은 `MAX(prices.date)`(시장의 마지막 날)이다 → Task 3.3 `test_export_targets_flags_stale_prices_relative_to_market_last_date`.

---

# Phase 0 — 환경 복구 (오늘, 코드 변경 2건)

목표: 이 PC에서 저장소가 다시 실행·테스트되고, SPA에 데이터가 보이며, 서버가 로그온 시 자동으로 뜬다. Task 0.4·0.5만 코드다. 나머지는 운영 절차라 테스트 대신 "Run/Expected"로 검증한다.

### Task 0.1: 작업 트리 복구

**Files:** 없음 (git 작업만)

누락은 2026-10-09 복원 때부터였고 Drive와 무관하다 (spec §1 — Drive 첫 실행은 2026-10-12). 원인은 더 조사하지 않고 HEAD에서 되살린다.

- [ ] **Step 1: 수정 파일이 없는지 확인**

Run (PowerShell, 저장소 루트):
```powershell
(git status --short | Select-String '^ M').Count
(git status --short | Select-String '^ D').Count
```
Expected: `0` 그리고 `82`. 첫 값이 0이 아니면 멈추고 사용자에게 보고한다 (restore가 수정을 지운다).

- [ ] **Step 2: 삭제된 추적 파일 복구**

Run: `git restore .`
Expected: 출력 없음.

- [ ] **Step 3: 확인**

Run: `git status --short --untracked-files=no; (git ls-files | Measure-Object -Line).Lines`
Expected: 빈 status, `158`. (`--untracked-files=no`를 빼면 원래 미추적인 `.omc/`·`data/`·`handoff/`·`reports/output/`과 이 계획서·spec이 `??`로 보인다.)

### Task 0.2: Drive 동기화 정리 — 저장소는 동기화 중지, DB 백업 폴더만 동기화 (사용자 확인)

**Files:**
- Modify: `.gitignore` (`data/*.duckdb.wal` 다음 줄에 `data/backups/` — 지금 규칙 `data/*.duckdb`는 하위 폴더를 거르지 않는다)

**배경** (spec §1): 프로젝트 폴더 자체가 Drive '내 컴퓨터'의 양방향 미러 동기화 폴더다(2026-10-12 22:15 등록). Drive는 이 폴더에 쓰기도 한다 — 2026-10-13 06:26·14:25(KST, 각각 Drive 재시작 직후)에 757건을 폴더 안으로 내려받았다. 위험은 셋이다. (a) 재연결·충돌 때 클라우드 사본이 `.git`·작업 트리를 덮어쓸 수 있다. (b) Drive는 파일마다 따로 올리므로 실행 중 올라간 DuckDB 본 파일과 `.wal` 사본은 시점이 어긋날 수 있어 복원용으로 믿을 수 없다. (c) 동기화량 대부분이 PC 전용 `.venv`(23,506파일·749MB)다. 코드는 GitHub(`origin`)에 전부 있으므로 Drive로 지킬 것은 DB뿐이다. 82개 누락은 Drive와 무관하다 (Task 0.1). **폴더는 옮기지 않는다** — 경로가 바뀌면 Claude Code 프로젝트 메모리(`~/.claude/projects/C---PYTHON-0-CK-Project-13--13f-tracker/`)가 이어지지 않는다.

Step 1·3은 사용자가 Drive 환경설정에서 한다. 구현 에이전트는 절차를 안내하고, 끝났다는 답을 받은 뒤 다음 Step으로 간다. **Step 1~3 사이에는 DB를 바꾸는 명령(`collect`·`analyze`·`backtest`·`update`)을 실행하지 않는다.**

- [ ] **Step 1: (사용자) 저장소 폴더의 동기화를 중지한다**

Drive 환경설정 → 내 컴퓨터 → `13. 13f-tracker` → 'Google Drive와 동기화' 해제 → 확인 창에 "‘13. 13f-tracker’에 새로 추가되는 파일이 더 이상 Google Drive에 동기화되지 않습니다. 기존 파일은 컴퓨터에 유지됩니다."가 나오면 확인 → 저장. `0. Research`·`cae-copilot`은 건드리지 않는다. Drive 웹에 옛 사본이 남으면 그대로 둔다 (지울지는 사용자 판단).

- [ ] **Step 2: `.gitignore`에 `data/backups/`를 넣고 DB 사본을 만든다** (Task 1.2와 같은 이름 규칙)

`.gitignore`의 `data/*.duckdb.wal` 다음 줄에 `data/backups/`를 추가한 뒤 실행한다.

Run (PowerShell, 저장소 루트):
```powershell
Test-Path data\13f.duckdb.wal
New-Item -ItemType Directory -Force data\backups | Out-Null
Copy-Item data\13f.duckdb ("data\backups\13f-{0:yyyyMMdd-HHmmss}.duckdb" -f (Get-Date))
Get-ChildItem data\backups | Select-Object Name, Length
git check-ignore -q data/backups/x.duckdb; $LASTEXITCODE
```
Expected: 첫 줄 `False`, `13f-YYYYMMDD-HHMMSS.duckdb` 1개(크기 = `data\13f.duckdb`), 마지막 줄 `0`. 첫 줄이 `True`면 복사하지 말고 멈춰 사용자에게 보고한다 — 어떤 프로세스가 DB에 쓰는 중이다.

- [ ] **Step 3: (사용자) `data\backups`를 새 동기화 폴더로 등록한다**

Drive 환경설정 → 내 컴퓨터 → 폴더 추가 → `C:\_PYTHON\0_CK_Project\13. 13f-tracker\data\backups` → 'Google Drive와 동기화' → 저장. Step 1에서 상위 폴더 동기화를 먼저 끊어야 두 동기화 폴더가 겹치지 않는다. 이후 Task 1.2의 자동 백업(최근 3개)이 이 폴더에 쌓여 Drive에 올라간다.

- [ ] **Step 4: 확인**

Run:
```powershell
if (-not (Get-ChildItem .tmp.driveupload -Force -ErrorAction SilentlyContinue)) { Remove-Item .tmp.driveupload -ErrorAction SilentlyContinue }
git status --short --untracked-files=no; git status --short --untracked-files=no
Test-Path .tmp.driveupload
Select-String -Path "$env:LOCALAPPDATA\Google\DriveFS\Logs\drive_fs*.txt" -SimpleMatch 'title: "backups"' | Select-Object -Last 1
```
Expected: 빈 status, `Test-Path` → `False` (git이 `.git`을 건드려도 Drive 임시 폴더가 다시 생기지 않는다), 마지막 명령에 `title: "backups"` 한 줄. 사용자가 Drive 웹(drive.google.com → 컴퓨터)의 `backups`에서 Step 2 사본을 확인하면 끝.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore data/backups for DuckDB backup copies"
```

### Task 0.3: venv 재생성

**Files:** 없음 (`.venv/`·`.python-version`은 gitignore)

- [ ] **Step 1: 깨진 venv를 다시 만든다**

Run: `uv python pin 3.14; uv sync`
Expected: `.python-version`에 `3.14`, `.venv` 재생성, `Installed N packages`. (`uv.lock`은 3.12·3.14 모두에서 설치됨을 점검에서 확인했다.)

- [ ] **Step 2: 인터프리터 확인**

Run: `uv run python -c "import sys, thirteen_f; print(sys.version)"`
Expected: `3.14.8 …`. 대신 `uv trampoline failed to spawn Python child process (os error 4551)` 또는 `An Application Control policy has blocked this file`가 나오면 Smart App Control 차단이다 → Task 0.4를 먼저 한다.

- [ ] **Step 3: 회귀 기준 확인**

Run: `uv run pytest tests/unit -q`
Expected: `204 passed`.

### Task 0.4: Smart App Control 우회 래퍼 (차단이 확인된 경우에만)

**Files:**
- Create: `scripts/py.ps1`
- Modify: `_claude_docs/TROUBLESHOOTING.md` (## 테스트·도구 절에 항목 추가)

**Interfaces:**
- Produces: `scripts\py.ps1 <python 인자…>` — `.venv/pyvenv.cfg`의 `home`이 가리키는 uv 관리 인터프리터를 직접 실행하고 `PYTHONPATH`에 저장소 루트·`src`·`.venv\Lib\site-packages`를 넣는다. Task 0.6·3.2의 스케줄러 스크립트가 이 래퍼를 부른다.

- [ ] **Step 1: 래퍼 작성**

```powershell
# scripts/py.ps1 — Smart App Control이 .venv\Scripts\python.exe(uv 런처)를 막을 때
# pyvenv.cfg의 home 인터프리터를 직접 실행한다. 사용: scripts\py.ps1 -m pytest tests/unit -q
param([Parameter(ValueFromRemainingArguments = $true)] [string[]] $PyArgs)
$root = Split-Path $PSScriptRoot -Parent
$cfg = Get-Content (Join-Path $root '.venv\pyvenv.cfg')
$home_ = ($cfg | Select-String '^home = (.+)$').Matches[0].Groups[1].Value.Trim()
$python = Join-Path $home_ 'python.exe'
$env:PYTHONPATH = "$root;$root\src;$root\.venv\Lib\site-packages"
& $python @PyArgs
exit $LASTEXITCODE
```

- [ ] **Step 2: 동작 확인**

Run: `scripts\py.ps1 -c "import sys, thirteen_f, duckdb; print(sys.version)"`
Expected: `3.14.8 …`.

Run: `scripts\py.ps1 -m pytest tests/unit -q`
Expected: `204 passed`.

- [ ] **Step 3: TROUBLESHOOTING에 항목 추가**

`## 테스트·도구`에 한 항목: 증상 `uv run …`이 `os error 4551`/`Application Control policy has blocked` — 원인 Smart App Control이 uv venv 런처를 간헐적으로 차단(2026-10-16~, `_brain` [[windows-smart-app-control-python-block]]) — 조치 `scripts\py.ps1 <python 인자>`로 실행, 해제 여부는 `Get-MpComputerStatus | Select SmartAppControlState`와 CodeIntegrity 3077 이벤트로 확인.

- [ ] **Step 4: Commit**

```bash
git add scripts/py.ps1 _claude_docs/TROUBLESHOOTING.md
git commit -m "chore(scripts): add py.ps1 to run the venv interpreter directly when SAC blocks the launcher"
```

### Task 0.5: integration `test_serve.py`를 uv 없이 실행

**Files:**
- Modify: `tests/integration/test_serve.py:27-43`

**Interfaces:**
- Produces: 서버 프로세스를 `[sys.executable, "-m", "thirteen_f.cli", "serve", "--port", …]`로 띄운다. `uv` 의존(skipif)과 SAC 차단·`thirteen-f.exe` 잠금 문제가 사라진다.

- [ ] **Step 1: 테스트 수정**

`@pytest.mark.skipif(shutil.which("uv") is None, …)`를 지우고 `Popen` 인자를 `[sys.executable, "-m", "thirteen_f.cli", "serve", "--port", str(port)]`로 바꾼다. 모듈 docstring의 "Skipped if uv is unavailable" 문장을 "현재 인터프리터로 `thirteen_f.cli serve`를 띄운다"로 바꾼다. `shutil` import가 더 이상 쓰이지 않으면 지운다. `taskkill /T` 정리는 그대로 둔다.

- [ ] **Step 2: 실행**

Run: `uv run pytest tests/integration/test_serve.py -q`
Expected: `1 passed` (약 5초). `uv run`이 막힌 환경에서는 `scripts\py.ps1 -m pytest tests/integration/test_serve.py -q`.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_serve.py
git commit -m "test(integration): launch serve with sys.executable instead of uv run"
```

### Task 0.6: export → serve 확인 → 서버 자동 시작 등록

**Files:**
- Modify: `_claude_docs/WORKFLOWS.md` (새 절 "## 서버 자동 시작")

- [ ] **Step 1: JSON dump 생성**

Run: `uv run thirteen-f export`
Expected: `OK Exported to src\thirteen_f\web\data`, `src/thirteen_f/web/data/targets.json` 존재, `git status --short --untracked-files=no` 여전히 빈 출력(`web/data/`는 gitignore).

- [ ] **Step 2: 서버 확인**

Run (별도 터미널): `uv run thirteen-f serve` 후 `curl.exe -s http://127.0.0.1:8765/api/health`
Expected: `{"llm_available": …}`. 브라우저 `http://127.0.0.1:8765/#/plan`에 전략 8개 표와 목표 비중이 보인다.

- [ ] **Step 3: 작업 스케줄러 등록 (사용자 확인 후 실행)**

```powershell
$root = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\py.ps1`" -m thirteen_f.cli serve"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "13f-serve" -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings $settings
Start-ScheduledTask -TaskName "13f-serve"
```
Run: `Start-Sleep 5; curl.exe -s http://127.0.0.1:8765/api/health`
Expected: 200 응답. (SAC가 풀린 상태라도 `py.ps1` 경로는 그대로 동작하므로 바꿀 필요가 없다. Tailscale은 이 PC에 없으므로 원격 접속 복구는 별도.)

- [ ] **Step 4: WORKFLOWS.md에 "서버 자동 시작" 절 추가 후 Commit**

위 PowerShell과 해제 명령(`Unregister-ScheduledTask -TaskName 13f-serve -Confirm:$false`)을 적는다.

```bash
git add _claude_docs/WORKFLOWS.md
git commit -m "docs: describe the serve scheduled task"
```

### Phase 0 DoD

- `git status --short --untracked-files=no` 빈 출력, 추적 파일 158개.
- Drive: 저장소 폴더는 동기화 중지, `data\backups`만 동기화 폴더로 등록돼 DB 사본 1개가 올라가 있다 (Task 0.2).
- `uv run pytest tests/unit -q`(또는 `scripts\py.ps1 -m pytest …`) → `204 passed`; integration `test_serve.py` 1 passed.
- `/api/health` 200, Plan 탭에 데이터 표시, (승인 시) 스케줄러 작업 `13f-serve` 등록.
- 멈추고 사용자 승인을 받은 뒤 Phase 1로.

---

# Phase 1 — 정확성·운영 (2026-11-16 Q3 기한 전 코드, 11-17 이후 반영)

목표: 점수·목표 비중을 바꾸는 결함(exit 시그널, 분모, 천 달러 단위, ETF·복수 클래스)과 운영 함정(`update` 범위, 백업, 가격 재다운로드)을 Q3 수집 **전에** 고치고, 11-17 이후 한 번의 루틴으로 Q3를 반영한 뒤 스윕을 한 번만 다시 돈다. Task 1.1~1.7은 코드, 1.8은 운영이다.

### Task 1.1: `update`가 DB 범위를 `collect --start`로 넘긴다

**Files:**
- Create: `src/thirteen_f/core/db_tools.py`
- Modify: `src/thirteen_f/cli.py:242-284` (`update`)
- Create: `tests/unit/test_db_tools.py`, `tests/unit/test_cli_update.py`
- Modify: `CLAUDE.md`(Commands의 `update` 주석), `README.md:50-53`, `_claude_docs/WORKFLOWS.md`("새 분기 13F 반영" 1번), `_claude_docs/TROUBLESHOOTING.md`(`thirteen-f update` 후 범위 증가 항목 삭제 — 해결됨)

**Interfaces:**
- Produces: `db_start_quarter(db_path: Path) -> str | None` (`core/db_tools.py`) — `filings.period_of_report`의 최소값을 `quarter_label`로 (`2024Q1`); 파일이 없거나 filings가 비면 `None`. read-only 연결.
- Produces: `update(start: str | None = typer.Option(None, "--start", help=…), skip_collect…, …)` — `--start`가 없으면 `db_start_quarter(settings.duckdb_path)`를 쓰고, 그것도 `None`이면 `collect`를 인자 없이(기본 2011Q1) 부른다.
- Consumes: `thirteen_f.core.dates.quarter_label(d: date) -> str`.

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/unit/test_db_tools.py`**

```python
from datetime import date
from pathlib import Path

import duckdb

from scripts.init_db import init_db
from thirteen_f.core.db_tools import db_start_quarter


def _db(tmp_path: Path, periods: list[date]) -> Path:
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    for i, p in enumerate(periods):
        c.execute("INSERT INTO filings VALUES (?, 'c1', '13F-HR', ?, ?, FALSE, NULL)", (f"a{i}", p, p))
    c.close()
    return db


def test_db_start_quarter_is_the_earliest_filing_quarter(tmp_path):
    db = _db(tmp_path, [date(2024, 6, 30), date(2024, 3, 31), date(2025, 3, 31)])
    assert db_start_quarter(db) == "2024Q1"


def test_db_start_quarter_is_none_for_empty_or_missing_db(tmp_path):
    assert db_start_quarter(_db(tmp_path, [])) is None
    assert db_start_quarter(tmp_path / "nope.duckdb") is None
```

- [ ] **Step 2: 실패하는 테스트 작성 — `tests/unit/test_cli_update.py`**

```python
"""`thirteen-f update` — 하위 단계 호출 인자 검증 (subprocess.run을 가짜로 바꿔 기록)."""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from typer.testing import CliRunner

from scripts.init_db import init_db
from thirteen_f.cli import app


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "13f.duckdb"
    init_db(db_path)
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    return db_path


def _with_filing(db_path: Path, period: date) -> None:
    c = duckdb.connect(str(db_path))
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    c.execute("INSERT INTO filings VALUES ('a1', 'c1', '13F-HR', ?, ?, FALSE, NULL)", (period, period))
    c.close()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    recorded: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        recorded.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return recorded


def _steps(calls: list[list[str]]) -> list[list[str]]:
    return [c[3:] for c in calls]  # [sys.executable, "-m", "thirteen_f.cli", *args]


def test_update_passes_db_start_quarter_to_collect(db, calls):
    _with_filing(db, date(2024, 3, 31))
    r = CliRunner().invoke(app, ["update", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls) == [["collect", "--start", "2024Q1"], ["analyze"]]


def test_update_explicit_start_wins(db, calls):
    _with_filing(db, date(2024, 3, 31))
    r = CliRunner().invoke(app, ["update", "--start", "2020Q1", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls)[0] == ["collect", "--start", "2020Q1"]


def test_update_with_empty_db_uses_collect_default_range(db, calls):
    r = CliRunner().invoke(app, ["update", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls)[0] == ["collect"]


def test_update_skip_collect_runs_no_collect(db, calls):
    r = CliRunner().invoke(app, ["update", "--skip-collect", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    assert _steps(calls) == [["analyze"]]
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/unit/test_db_tools.py tests/unit/test_cli_update.py -q`
Expected: FAIL — `ModuleNotFoundError: thirteen_f.core.db_tools`, 그리고 `--start` 옵션 없음.

- [ ] **Step 4: 구현**

`core/db_tools.py`에 `db_start_quarter`. `cli.update`는 함수 안에서 `load_settings()`·`db_start_quarter`를 import하고 collect 인자를 조립해 `run_step`에 넘긴다. 유도한 범위는 `typer.echo(f"collect range: --start {label} (DB 최소 분기)")`로 보여 준다.

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS (204 + 6).

- [ ] **Step 6: 문서 갱신 후 Commit**

CLAUDE.md Commands의 `update` 줄 주석을 "collect는 DB의 최소 분기부터(`--start`로 바꿀 수 있음)"로, README 50-53줄의 경고를 같은 내용으로, WORKFLOWS 1번을 `uv run thirteen-f update …` 중심으로, TROUBLESHOOTING의 해당 항목은 삭제한다.

```bash
git add src/thirteen_f/core/db_tools.py src/thirteen_f/cli.py tests/unit/test_db_tools.py tests/unit/test_cli_update.py CLAUDE.md README.md _claude_docs/WORKFLOWS.md _claude_docs/TROUBLESHOOTING.md
git commit -m "fix(cli): make update collect from the DB's earliest quarter instead of 2011Q1"
```

### Task 1.2: `update` 시작 시 DuckDB 자동 백업

**Files:**
- Modify: `src/thirteen_f/core/db_tools.py`, `src/thirteen_f/cli.py`(`update`) — `.gitignore`의 `data/backups/`는 Task 0.2에서 넣었다
- Modify: `tests/unit/test_db_tools.py`, `tests/unit/test_cli_update.py`
- Modify: `_claude_docs/WORKFLOWS.md`("새 분기 13F 반영" 1번의 수동 백업 문장 → 자동 백업 언급), `CLAUDE.md` Workflow Rules의 DuckDB 유일본 항목에 "update는 `data/backups/`(Google Drive 동기화 폴더)에 최근 3개를 남긴다" 한 문장

**Interfaces:**
- Produces: `backup_db(db_path: Path, keep: int = 3) -> Path | None` — 최종 경로는 `db_path.parent / "backups" / f"{db_path.stem}-{YYYYMMDD-HHMMSS}{db_path.suffix}"`. `backups/`는 Drive 동기화 폴더(Task 0.2)라서, 동기화되지 않는 `db_path.parent / f".{최종 이름}.partial"`에 먼저 `shutil.copy2`한 뒤 `os.replace`로 옮긴다 — Drive가 반쯤 쓴 105MB 파일을 올리지 않게. 같은 폴더의 같은 stem 백업을 이름순으로 정렬해 최신 `keep`개만 남기고 삭제(삭제도 Drive에 반영된다), 만든 경로 반환. `db_path`가 없으면 `None`.
- `update`는 첫 단계 전에 `backup_db(settings.duckdb_path)`를 부르고 `typer.echo(f"backup: {path}")`.

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/unit/test_db_tools.py`**

```python
import re
from thirteen_f.core.db_tools import backup_db


def test_backup_db_copies_file_with_timestamp_name(tmp_path):
    db = tmp_path / "13f.duckdb"
    db.write_bytes(b"duck")
    out = backup_db(db)
    assert out is not None and out.parent == tmp_path / "backups"
    assert re.fullmatch(r"13f-\d{8}-\d{6}\.duckdb", out.name)
    assert out.read_bytes() == b"duck"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".partial")] == []


def test_backup_db_keeps_only_the_newest_three(tmp_path):
    db = tmp_path / "13f.duckdb"
    db.write_bytes(b"duck")
    bdir = tmp_path / "backups"
    bdir.mkdir()
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (bdir / f"13f-{stamp}.duckdb").write_bytes(b"old")
    backup_db(db, keep=3)
    names = sorted(p.name for p in bdir.iterdir())
    assert len(names) == 3 and "13f-20260101-000000.duckdb" not in names


def test_backup_db_returns_none_when_db_missing(tmp_path):
    assert backup_db(tmp_path / "none.duckdb") is None
```

`tests/unit/test_cli_update.py`에 추가:

```python
def test_update_backs_up_db_before_first_step(db, calls):
    r = CliRunner().invoke(app, ["update", "--skip-collect", "--skip-backtest", "--skip-export", "--skip-report"])
    assert r.exit_code == 0, r.output
    backups = list((db.parent / "backups").iterdir())
    assert len(backups) == 1 and "backup:" in r.output
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/test_db_tools.py tests/unit/test_cli_update.py -q`
Expected: FAIL — `ImportError: backup_db`.

- [ ] **Step 3: 구현** (`backup_db` + `update` 호출)

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS.

- [ ] **Step 5: 문서 갱신 후 Commit**

```bash
git add src/thirteen_f/core/db_tools.py src/thirteen_f/cli.py tests/unit/test_db_tools.py tests/unit/test_cli_update.py _claude_docs/WORKFLOWS.md CLAUDE.md
git commit -m "feat(cli): back up the DuckDB file before update runs"
```

### Task 1.3: 청산(`exit`)·재진입 시그널 복구

**Files:**
- Modify: `src/thirteen_f/analyze/diff.py:39-93` (`compute_signals_quarterly`의 SQL)
- Create: `tests/unit/analyze/test_diff_sql.py`
- Modify: `_claude_docs/ARCHITECTURE.md:31`(analyze 1번 설명), `_claude_docs/DATA_FORMATS.md`(`signals_quarterly` 행 의미: exit 행은 shares 0·weight_pct 0·shares_change 음수)

**Interfaces:**
- Produces: `compute_signals_quarterly(conn, threshold=0.05) -> int` — 시그니처 그대로. 결과 행 = 보유 행(shares > 0) + **청산 분기 행**(직전 제출 분기엔 있었고 이번 제출 분기엔 없는 종목: `change_type='exit'`, `shares_change = -prev`, `value_change_usd = -prev_value`, `weight_pct = 0`). 청산 뒤 0주 행은 만들지 않는다. "제출 분기"는 holdings가 1행 이상 있는 유효 필링(`superseded_by IS NULL`)의 분기다.
- Consumes: 기존 CTE `effective`, `agg_per_filing`, `portfolio_total`; 하류 `update_conviction_scores`, `update_continuity_scores`, `compute_consensus`, `compute_total_scores`는 바꾸지 않는다 (`!= 'exit'` 필터가 이제 의미를 갖는다). `web/ask_context.py`·`llm/summary.py`·Quarto의 change_type 집계에 exit가 나타나는 것은 의도된 결과다.

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/unit/analyze/test_diff_sql.py`**

```python
"""compute_signals_quarterly의 SQL 경로 — 청산(exit)·재진입(new) 행 생성."""
from datetime import date, timedelta

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.analyze.continuity import update_continuity_scores
from thirteen_f.analyze.conviction import update_conviction_scores
from thirteen_f.analyze.diff import compute_signals_quarterly
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager

Q1, Q2, Q3 = date(2024, 3, 31), date(2024, 6, 30), date(2024, 9, 30)


def _mgr(c, cik):
    upsert_manager(c, {"cik": cik, "name": cik, "label": cik, "fund": "F", "style": "value",
                       "active_since": 2020, "cloning_score_weight": 1.0})


def _filing(c, acc, cik, period):
    upsert_filing(c, {"accession_no": acc, "cik": cik, "form_type": "13F-HR", "period_of_report": period,
                      "filed_at": period + timedelta(days=45), "is_amendment": False})


def _h(cusip, shares):
    return {"cusip": cusip, "name_of_issuer": cusip, "title_of_class": "COM", "value_usd": shares * 10,
            "shares": shares, "share_type": "SH", "put_call": ""}


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    _mgr(c, "m1"); _mgr(c, "m2")
    for acc, cik, p in [("m1q1", "m1", Q1), ("m1q2", "m1", Q2), ("m1q3", "m1", Q3), ("m2q1", "m2", Q1), ("m2q2", "m2", Q2)]:
        _filing(c, acc, cik, p)
    upsert_holdings(c, "m1q1", [_h("AAA", 100), _h("BBB", 50)])
    upsert_holdings(c, "m1q2", [_h("AAA", 100)])                # BBB 전량 매도
    upsert_holdings(c, "m1q3", [_h("BBB", 60), _h("CCC", 10)])  # AAA 전량 매도, BBB 재진입, CCC 신규
    upsert_holdings(c, "m2q1", [_h("AAA", 10)])                 # m2q2는 holdings 없음 (information table 누락 상황)
    yield c
    c.close()


def _types(conn, cik, cusip):
    return dict(conn.execute(
        "SELECT period_of_report, change_type FROM signals_quarterly WHERE cik = ? AND cusip = ? ORDER BY 1",
        (cik, cusip)).fetchall())


def test_full_liquidation_emits_exit_row(conn):
    compute_signals_quarterly(conn)
    assert _types(conn, "m1", "AAA") == {Q1: "new", Q2: "hold", Q3: "exit"}
    row = conn.execute(
        "SELECT shares_change, value_change_usd, weight_pct FROM signals_quarterly "
        "WHERE cik = 'm1' AND cusip = 'AAA' AND period_of_report = ?", (Q3,)).fetchone()
    assert row == (-100, -1000, 0.0)


def test_reentry_after_gap_is_new_again(conn):
    compute_signals_quarterly(conn)
    assert _types(conn, "m1", "BBB") == {Q1: "new", Q2: "exit", Q3: "new"}


def test_no_rows_after_exit_and_no_exit_for_unparsed_or_missing_filings(conn):
    n = compute_signals_quarterly(conn)
    assert _types(conn, "m2", "AAA") == {Q1: "new"}   # holdings 없는 m2q2는 제출로 보지 않는다 → 거짓 exit 없음
    assert n == 3 + 3 + 1 + 1                          # AAA 3 + BBB 3 + CCC 1 + m2/AAA 1


def test_exit_rows_feed_consensus_and_continuity(conn):
    compute_signals_quarterly(conn)
    update_conviction_scores(conn)
    update_continuity_scores(conn)
    compute_consensus(conn)
    assert conn.execute("SELECT 1 FROM consensus_quarterly WHERE cusip = 'BBB' AND period_of_report = ?",
                        (Q2,)).fetchone() is None                 # 청산한 분기엔 보유자 아님
    assert conn.execute("SELECT new_buy_count FROM consensus_quarterly WHERE cusip = 'BBB' AND period_of_report = ?",
                        (Q3,)).fetchone()[0] == 1                 # 재진입은 신규 매수
    assert conn.execute("SELECT continuity_score FROM signals_quarterly WHERE cik = 'm1' AND cusip = 'BBB' "
                        "AND period_of_report = ?", (Q3,)).fetchone()[0] == pytest.approx(0.25)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/analyze/test_diff_sql.py -q`
Expected: 4 FAIL — `{Q1: 'new', Q2: 'hold'}`처럼 exit 행이 없다.

- [ ] **Step 3: SQL 구현**

`agg_per_filing` 뒤에 격자를 만들고 `lagged`는 격자 위에서 LAG한다. 마지막 `WHERE`가 청산 뒤 0주 행을 걸러낸다. CASE·SELECT 목록은 기존 그대로.

```sql
filed_periods AS (                      -- holdings가 있는 유효 필링의 (cik, 분기)
    SELECT DISTINCT cik, period_of_report FROM effective
),
held_pairs AS (                         -- 매니저가 한 번이라도 보유한 종목과 첫 보유 분기
    SELECT cik, cusip, MIN(period_of_report) AS first_period FROM agg_per_filing GROUP BY cik, cusip
),
grid AS (                               -- 첫 보유 분기 이후의 모든 제출 분기, 미보유는 0
    SELECT fp.cik, fp.period_of_report, hp.cusip,
           COALESCE(a.shares, 0) AS shares, COALESCE(a.value_usd, 0) AS value_usd
    FROM filed_periods fp
    JOIN held_pairs hp ON hp.cik = fp.cik AND fp.period_of_report >= hp.first_period
    LEFT JOIN agg_per_filing a
           ON a.cik = fp.cik AND a.cusip = hp.cusip AND a.period_of_report = fp.period_of_report
),
lagged AS (
    SELECT g.cik, g.period_of_report, g.cusip, g.shares, g.value_usd, p.total_value,
           LAG(g.shares)    OVER (PARTITION BY g.cik, g.cusip ORDER BY g.period_of_report) AS prev_shares,
           LAG(g.value_usd) OVER (PARTITION BY g.cik, g.cusip ORDER BY g.period_of_report) AS prev_value
    FROM grid g LEFT JOIN portfolio_total p USING (cik, period_of_report)
)
SELECT …기존 SELECT 그대로…
FROM lagged
WHERE shares > 0 OR COALESCE(prev_shares, 0) > 0   -- 보유 행 + 청산 분기 행만
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS. `test_consensus.py`·`test_continuity.py`는 영향 없음.

- [ ] **Step 5: 문서 갱신 후 Commit**

ARCHITECTURE analyze 1번에 "전량 매도된 종목은 다음 제출 분기에 `exit` 행(0주)으로 남고, 공백 뒤 재진입은 `new`"를 적는다. DATA_FORMATS `signals_quarterly` 행에 exit 행 값 규칙을 적는다.

```bash
git add src/thirteen_f/analyze/diff.py tests/unit/analyze/test_diff_sql.py _claude_docs/ARCHITECTURE.md _claude_docs/DATA_FORMATS.md
git commit -m "fix(analyze): emit exit rows for liquidated holdings so re-entries count as new"
```

### Task 1.4: 컨센서스 분모 = 그 분기 제출자 수

**Files:**
- Modify: `src/thirteen_f/analyze/score.py:49-98`, `src/thirteen_f/analyze/pipeline.py:34-35`
- Modify: `tests/unit/analyze/test_score.py` (DB 테스트 추가)
- Modify: `_claude_docs/ARCHITECTURE.md:35` (analyze 5번: "보유 거장 수 ÷ 그 분기에 유효 필링을 낸 거장 수")

**Interfaces:**
- Produces: `compute_total_scores(conn, weights) -> int` — `manager_count` 파라미터 제거(호출자는 `pipeline.py` 하나). `consensus_score = holder_count / filers(period)`, `filers(period) = COUNT(DISTINCT cik) FROM filings WHERE superseded_by IS NULL GROUP BY period_of_report`. `total_score`의 첫 항도 같은 값.
- Consumes: Task 1.3의 signals 결과(테스트는 파이프라인 함수를 순서대로 부른다).

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/unit/analyze/test_score.py`**

```python
from datetime import date, timedelta

import duckdb

from scripts.init_db import init_db
from thirteen_f.analyze.consensus import compute_consensus
from thirteen_f.analyze.continuity import update_continuity_scores
from thirteen_f.analyze.conviction import update_conviction_scores
from thirteen_f.analyze.diff import compute_signals_quarterly
from thirteen_f.analyze.score import compute_total_scores
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager

Q1, Q2 = date(2024, 3, 31), date(2024, 6, 30)


def _h(cusip, shares=10):
    return {"cusip": cusip, "name_of_issuer": cusip, "title_of_class": "COM", "value_usd": shares * 10,
            "shares": shares, "share_type": "SH", "put_call": ""}


def test_consensus_score_divides_by_that_quarters_filers(tmp_path):
    """Q1은 3명 제출·전원 AAA 보유, Q2는 2명만 제출 — 분모는 명단(3)이 아니라 제출자(2)."""
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    for cik in ("c1", "c2", "c3"):
        upsert_manager(c, {"cik": cik, "name": cik, "label": cik, "fund": "F", "style": "value",
                           "active_since": 2020, "cloning_score_weight": 1.0})
    for acc, cik, p in [("a1", "c1", Q1), ("a2", "c2", Q1), ("a3", "c3", Q1), ("b1", "c1", Q2), ("b2", "c2", Q2)]:
        upsert_filing(c, {"accession_no": acc, "cik": cik, "form_type": "13F-HR", "period_of_report": p,
                          "filed_at": p + timedelta(days=45), "is_amendment": False})
        upsert_holdings(c, acc, [_h("AAA")] + ([_h("BBB")] if acc == "b1" else []))
    compute_signals_quarterly(c); update_conviction_scores(c); update_continuity_scores(c); compute_consensus(c)
    compute_total_scores(c, ScoreWeights(consensus=0.3, conviction=0.3, continuity=0.2, cloning_quality=0.2))
    score = {(p, cu): s for p, cu, s in c.execute(
        "SELECT period_of_report, cusip, consensus_score FROM total_scores").fetchall()}
    assert score[(Q1, "AAA")] == pytest.approx(1.0)
    assert score[(Q2, "AAA")] == pytest.approx(1.0)   # 2/2 — 종전 로직이면 2/3
    assert score[(Q2, "BBB")] == pytest.approx(0.5)
    c.close()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/analyze/test_score.py -q`
Expected: FAIL — `score[(Q2, "AAA")] == 0.6667`.

- [ ] **Step 3: 구현** — `score.py`에 `filers` CTE를 넣고 `?` 분모를 `fl.n`으로 바꾼다(`JOIN filers fl ON fl.period_of_report = a.period_of_report`). `pipeline.py:35`를 `compute_total_scores(conn, weights)`로.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/analyze/score.py src/thirteen_f/analyze/pipeline.py tests/unit/analyze/test_score.py _claude_docs/ARCHITECTURE.md
git commit -m "fix(analyze): divide consensus by the quarter's filers, not the roster size"
```

### Task 1.5: 천 달러 단위 보고 필링 보정

**Files:**
- Create: `src/thirteen_f/collect/value_units.py`
- Modify: `src/thirteen_f/collect/pipeline.py:163-172` (가격 단계 뒤에 호출, `stats["value_unit_fixed"]`)
- Create: `tests/unit/collect/test_value_units.py`
- Modify: `CLAUDE.md` Invariants "value 단위" 항목(한 문장 추가), `_claude_docs/ARCHITECTURE.md` collect 절(7번 단계), `_claude_docs/TROUBLESHOOTING.md`("Klarman·Druckenmiller의 금액이 1000배 작음" 항목 삭제 — 해결됨), `README.md:132`(Duquesne 천 달러 문장 → 보정됨)

**Interfaces:**
- Produces (`collect/value_units.py`):
  - `RATIO_THRESHOLD = 0.01`, `MIN_ROWS = 5`
  - `detect_thousand_unit_filings(conn) -> list[str]` — 유효 필링(`superseded_by IS NULL`)마다 `put_call = ''`·`shares > 0`·`value_usd > 0`·ticker 매핑·분기말 이하 마지막 `prices.close`가 있는 행의 `value_usd / (shares × close)` **중앙값**이 `RATIO_THRESHOLD` 미만이고 행 수가 `MIN_ROWS` 이상이면 그 `accession_no`. 정렬된 리스트.
  - `fix_thousand_unit_filings(conn) -> list[str]` — 감지된 필링의 `holdings.value_usd`를 ×1000 `UPDATE`하고 accession 리스트 반환. 보정 뒤 비율이 ~1이 되므로 재실행해도 빈 리스트(멱등).
- `run_collect`는 가격 다운로드 뒤 `fix_thousand_unit_filings(conn)`를 부르고 각 accession을 `logger.info`로 남긴다.

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/unit/collect/test_value_units.py`**

```python
from datetime import date

import duckdb
import pytest

from scripts.init_db import init_db
from thirteen_f.collect.loader import upsert_filing, upsert_holdings, upsert_manager
from thirteen_f.collect.value_units import detect_thousand_unit_filings, fix_thousand_unit_filings

Q1 = date(2024, 3, 31)


def _rows(n, value, put_call=""):
    return [{"cusip": f"C{i:08d}", "name_of_issuer": f"C{i}", "title_of_class": "COM", "value_usd": value,
             "shares": 10, "share_type": "SH", "put_call": put_call} for i in range(n)]


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    upsert_manager(c, {"cik": "m", "name": "M", "label": "M", "fund": "F", "style": "value",
                       "active_since": 2020, "cloning_score_weight": 1.0})
    for acc in ("k1", "n1", "s1"):
        upsert_filing(c, {"accession_no": acc, "cik": "m", "form_type": "13F-HR", "period_of_report": Q1,
                          "filed_at": date(2024, 5, 15), "is_amendment": False})
    for i in range(6):   # 티커 매핑 + 분기말 종가 100
        c.execute("INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, FALSE)", (f"C{i:08d}", f"T{i}"))
        c.execute("INSERT INTO prices (ticker, date, close, adj_close) VALUES (?, DATE '2024-03-28', 100.0, 100.0)", (f"T{i}",))
    upsert_holdings(c, "k1", _rows(6, value=1))      # 10주 × $100 = $1,000인데 value 1 → 비율 0.001 (천 달러 단위)
    upsert_holdings(c, "n1", _rows(6, value=1000))   # 정상
    upsert_holdings(c, "s1", _rows(3, value=1))      # 3행뿐 → 판정 보류
    yield c
    c.close()


def test_detects_filings_reported_in_thousands(conn):
    assert detect_thousand_unit_filings(conn) == ["k1"]


def test_fix_multiplies_by_1000_once(conn):
    assert fix_thousand_unit_filings(conn) == ["k1"]
    assert conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 'k1'").fetchone()[0] == 6000
    assert conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 'n1'").fetchone()[0] == 6000
    assert conn.execute("SELECT SUM(value_usd) FROM holdings WHERE accession_no = 's1'").fetchone()[0] == 3
    assert fix_thousand_unit_filings(conn) == []     # 멱등


def test_option_rows_are_ignored_in_detection(conn):
    # upsert_holdings는 같은 accession의 기존 행을 지우고 다시 넣으므로 전체 목록을 준다.
    # 정상 5행(비율 1) + 풋 6행(비율 0.001): 풋을 세면 중앙값이 0.001이라 오탐, 빼면 1.0
    upsert_holdings(conn, "n1", _rows(5, value=1000) + _rows(6, value=1, put_call="PUT"))
    assert detect_thousand_unit_filings(conn) == ["k1"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/collect/test_value_units.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현**

분기말 종가는 `(SELECT DISTINCT period_of_report FROM filings)` × `prices`를 `date <= period AND date > period - INTERVAL 10 DAY`로 조인해 `MAX_BY(close, date)`로 한 번에 구한다(행마다 상관 서브쿼리 금지 — 13k × 1.3M 행). 중앙값은 DuckDB `MEDIAN()`.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS (`test_pipeline.py`는 가격이 없어 보정 0건).

- [ ] **Step 5: 문서 갱신 후 Commit**

```bash
git add src/thirteen_f/collect/value_units.py src/thirteen_f/collect/pipeline.py tests/unit/collect/test_value_units.py CLAUDE.md _claude_docs/ARCHITECTURE.md _claude_docs/TROUBLESHOOTING.md README.md
git commit -m "fix(collect): rescale filings that report values in thousands of dollars"
```

### Task 1.6: 집계 전략의 ETF 제외·발행사 단위 합산

**Files:**
- Modify: `src/thirteen_f/backtest/strategies/consensus_top_k.py`, `score_top_k.py`, `new_buy_only.py`, `conviction_follow.py`, `multi_manager.py`
- Modify: `tests/unit/backtest/test_score_top_k.py`(fixture 확장 + 테스트), `tests/unit/backtest/test_other_strategies.py`, `tests/unit/backtest/test_multi_manager.py`
- Modify: `CLAUDE.md` Invariants(새 항목), `_claude_docs/ARCHITECTURE.md` backtest 절, `README.md:139`(주의사항 7 → 해결 내용), `_claude_docs/FRONTEND_PARITY.md`(TARGETS 행: Plan 탭의 GOOG·GOOGL/ETF 경고는 복제 전략에만 해당)

**Interfaces:**
- Produces — 두 규칙, `SingleManagerClone`(거장 보유 그대로 복제) 제외 5개 전략에 적용:
  - **R1 ETF 제외**: `LEFT JOIN cusip_ticker_map m ON m.cusip = …` 후 `COALESCE(m.is_etf, FALSE) = FALSE`.
  - **R2 발행사 합산**: 발행사 키 = `SUBSTR(cusip, 1, 6)`. 발행사당 티커 1개만 남긴다 — ConsensusTopK·ScoreTopK·NewBuyOnly는 `total_score` 최고 클래스, ConvictionFollow는 매니저별 `conviction_score` 최고 클래스, MultiManager는 클래스 합산 `value_usd`가 가장 큰 클래스(합산 금액으로 순위·비중). 보유자 수·신규매수 수의 문턱값은 클래스 중 **최대값**(`MAX(holder_count)`, `MAX(new_buy_count)`)으로 본다 — `holder_ciks` 문자열을 쪼개지 않아도 되고, 종전 의미(같은 클래스를 N명이 보유)와 어긋나지 않는 보수적 선택.
  - 두 규칙은 **`ROW_NUMBER`·`LIMIT` 전에** 적용한다 — 제외될 행이 top_k 자리를 차지하면 안 된다 (ConvictionFollow 테스트가 이를 강제한다).
- `get_target_positions` 시그니처·`params_json`·`name`은 그대로.

- [ ] **Step 1: fixture 확장 — `tests/unit/backtest/test_score_top_k.py`**

fixture의 `total_scores`/`consensus_quarterly` 삽입 뒤에 추가한다 (기존 5종목 테스트는 그대로 통과해야 한다):

```python
    # ETF(SPY)와 같은 발행사의 두 클래스(530307 = LBRDA/LBRDK)
    c.executemany(
        "INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
        [("037833100", "AAPL", False), ("037833200", "MSFT", False), ("037833300", "GOOG", False),
         ("037833400", "AMZN", False), ("037833500", "META", False),
         ("78462F103", "SPY", True), ("530307107", "LBRDA", False), ("530307305", "LBRDK", False)],
    )
    c.executemany(
        "INSERT INTO total_scores VALUES (?, ?, ?, 1.0, 1.0, 1.0, 1.0, ?)",
        [(date(2024, 3, 31), "78462F103", "SPY", 0.99),
         (date(2024, 3, 31), "530307107", "LBRDA", 0.41), (date(2024, 3, 31), "530307305", "LBRDK", 0.42)],
    )
    c.executemany(
        "INSERT INTO consensus_quarterly VALUES (?, ?, ?, ?, ?, ?, 0.5)",
        [(date(2024, 3, 31), "78462F103", "SPY", 7, 2, "c1,c2"),
         (date(2024, 3, 31), "530307107", "LBRDA", 2, 0, "c1,c2"),
         (date(2024, 3, 31), "530307305", "LBRDK", 2, 0, "c1,c3")],
    )
```
(LBRDA·LBRDK의 `new_buy_count`는 0으로 둔다 — 기존 `test_new_buy_only_holds_cash_below_min_positions`가 후보 2종목(AAPL·MSFT)을 전제하기 때문. SPY의 new_buy 2는 ETF 제외로 그 테스트에 영향이 없다.)

- [ ] **Step 2: 실패하는 테스트 추가 — 같은 파일**

```python
def test_consensus_top_k_excludes_etfs(conn):
    t = ConsensusTopK(min_holders=3, top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t                      # 7명 보유·최고 점수지만 is_etf


def test_consensus_top_k_keeps_one_share_class_per_issuer(conn):
    t = ConsensusTopK(min_holders=2, top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "LBRDK" in t and "LBRDA" not in t   # 발행사 530307 → total_score 높은 클래스만
    assert "AMZN" in t                         # 보유자 2명은 그대로 후보


def test_score_top_k_excludes_etfs_and_duplicate_classes(conn):
    t = ScoreTopK(top_k=10).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t
    assert {"LBRDA", "LBRDK"} & set(t) == {"LBRDK"}
    assert t["LBRDK"] == pytest.approx(1 / 6)  # AAPL MSFT GOOG AMZN META LBRDK


def test_new_buy_only_merges_classes_and_excludes_etfs(conn):
    conn.execute("UPDATE consensus_quarterly SET new_buy_count = 2 WHERE ticker = 'LBRDA'")
    conn.execute("UPDATE consensus_quarterly SET new_buy_count = 1 WHERE ticker = 'LBRDK'")
    t = NewBuyOnly(min_holders=2, top_k=15).get_target_positions(date(2024, 6, 1), conn)
    assert "SPY" not in t                      # new_buy 2명이지만 ETF
    assert "LBRDK" in t and "LBRDA" not in t   # 발행사 신규매수 수 = max(2, 1) = 2 → 대표 클래스는 total_score 높은 LBRDK
    assert set(t) == {"AAPL", "LBRDK"}         # AAPL new_buy 2, MSFT 1은 탈락
```

`tests/unit/backtest/test_other_strategies.py`에 ConvictionFollow 테스트 추가 (데이터는 테스트 안에서 만든다):

```python
def test_conviction_follow_excludes_etfs_and_merges_classes(empty_conn):
    c = empty_conn
    c.execute("INSERT INTO managers (cik, name) VALUES ('c1', 'M')")
    c.execute("INSERT INTO filings VALUES ('a1', 'c1', '13F-HR', DATE '2024-03-31', DATE '2024-05-15', FALSE, NULL)")
    c.executemany("INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
                  [("78462F103", "SPY", True), ("530307107", "LBRDA", False), ("530307305", "LBRDK", False),
                   ("037833100", "AAPL", False)])
    c.executemany(
        "INSERT INTO signals_quarterly (cik, cusip, period_of_report, change_type, weight_pct, conviction_score) "
        "VALUES ('c1', ?, DATE '2024-03-31', 'hold', 0.1, ?)",
        [("78462F103", 1.0), ("530307107", 0.9), ("530307305", 0.8), ("037833100", 0.7)],
    )
    t = ConvictionFollow(top_k=2).get_target_positions(date(2024, 6, 1), c)
    assert set(t) == {"LBRDA", "AAPL"}                      # SPY 제외, 발행사당 1개, 그다음 상위 2개
    assert t["LBRDA"] == pytest.approx(0.9 / 1.6)
```

`tests/unit/backtest/test_multi_manager.py`에 추가 (fixture의 cusip은 3자리 가짜라 접두사 6자리는 그 자체):

```python
def test_multi_manager_excludes_etfs_and_sums_share_classes(conn):
    conn.executemany("INSERT INTO cusip_ticker_map (cusip, ticker, is_etf) VALUES (?, ?, ?)",
                     [("78462F103", "SPY", True), ("530307107", "LBRDA", False), ("530307305", "LBRDK", False)])
    # upsert_holdings는 accession의 기존 행을 지우고 다시 넣는다 → fixture의 AAA·BBB를 포함한 전체 목록
    upsert_holdings(conn, "a1", [
        {"cusip": "AAA", "name_of_issuer": "Apple", "title_of_class": "COM", "value_usd": 1000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "BBB", "name_of_issuer": "Boeing", "title_of_class": "COM", "value_usd": 500, "shares": 5, "share_type": "SH", "put_call": ""},
        {"cusip": "78462F103", "name_of_issuer": "SPDR", "title_of_class": "ETF", "value_usd": 5000, "shares": 10, "share_type": "SH", "put_call": ""},
        {"cusip": "530307107", "name_of_issuer": "Liberty", "title_of_class": "A", "value_usd": 700, "shares": 7, "share_type": "SH", "put_call": ""},
        {"cusip": "530307305", "name_of_issuer": "Liberty", "title_of_class": "K", "value_usd": 600, "shares": 6, "share_type": "SH", "put_call": ""},
    ])
    s = MultiManager(mgr_labels=["M1", "M2"], top_k=2, weighting="byvalue")
    t = s.get_target_positions(date(2024, 6, 1), conn)
    # AAPL 1800, Liberty 700+600=1300(대표 LBRDA), KO 1200 → top 2 = AAPL, LBRDA. SPY 5000은 제외
    assert set(t) == {"AAPL", "LBRDA"}
    assert t["LBRDA"] == pytest.approx(1300 / 3100)
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/unit/backtest -q`
Expected: 새 테스트 6개 FAIL(SPY 포함, 두 클래스 모두 포함), 기존 테스트 PASS.

- [ ] **Step 4: 구현** — ConsensusTopK의 SQL(기준 형태; 나머지 4개는 같은 두 규칙을 각자의 SQL에 적용):

```sql
WITH cand AS (
    SELECT t.ticker, t.total_score, c.holder_count, SUBSTR(t.cusip, 1, 6) AS issuer
    FROM total_scores t
    JOIN consensus_quarterly c ON c.period_of_report = t.period_of_report AND c.cusip = t.cusip
    LEFT JOIN cusip_ticker_map m ON m.cusip = t.cusip
    WHERE t.period_of_report = ? AND t.ticker IS NOT NULL AND COALESCE(m.is_etf, FALSE) = FALSE
),
one_per_issuer AS (   -- 발행사당 total_score 최고 클래스, 보유자 수는 클래스 중 최대
    SELECT ticker, total_score, MAX(holder_count) OVER (PARTITION BY issuer) AS issuer_holders
    FROM cand
    QUALIFY ROW_NUMBER() OVER (PARTITION BY issuer ORDER BY total_score DESC NULLS LAST, ticker) = 1
)
SELECT ticker FROM one_per_issuer
WHERE issuer_holders >= ?
ORDER BY total_score DESC NULLS LAST
LIMIT ?
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS (`test_lookahead_guard.py` 포함).

- [ ] **Step 6: 문서 갱신 후 Commit**

CLAUDE.md Invariants에 "**집계 전략의 종목 단위**: ConsensusTopK·ScoreTopK·NewBuyOnly·ConvictionFollow·MultiManager는 `is_etf` 종목을 빼고 발행사(CUSIP 앞 6자리)당 한 클래스만 쓴다. 복제(SingleManagerClone)는 거장 보유 그대로."를 추가. README 주의사항 7을 "2026-11에 집계 전략에서 ETF 제외·발행사 합산을 적용했다(복제 전략은 제외)"로.

```bash
git add src/thirteen_f/backtest/strategies tests/unit/backtest CLAUDE.md _claude_docs/ARCHITECTURE.md README.md _claude_docs/FRONTEND_PARITY.md
git commit -m "feat(backtest): exclude ETFs and collapse share classes in aggregate strategies"
```

### Task 1.7: 가격 증분 다운로드 + 배당·분할 조정 재스케일

**Files:**
- Modify: `src/thirteen_f/collect/price_loader.py:130-156` (+ 헬퍼)
- Modify: `tests/unit/collect/test_price_loader.py`
- Modify: `_claude_docs/WORKFLOWS.md`("새 분기 13F 반영" 1번의 소요 시간 문장), `_claude_docs/TROUBLESHOOTING.md`("가격이 어느 날짜에서 끊김" ① — 새 티커는 전체 기간을 받는다는 문장 유지)

**Interfaces:**
- Produces (`price_loader.py`):
  - `OVERLAP_DAYS = 10`, `ADJ_TOLERANCE = 1e-4`
  - `_last_price_dates(conn) -> dict[str, date]` — `SELECT ticker, MAX(date) FROM prices GROUP BY ticker`.
  - `download_prices(conn, tickers, start, failure_log=None) -> dict[str, int]` — 시그니처 유지. 종목별 동작은 Step 3의 알고리즘.
- 호출자 `collect/pipeline.py`는 바꾸지 않는다.

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/unit/collect/test_price_loader.py`**

```python
from datetime import timedelta

from thirteen_f.collect import price_loader
from thirteen_f.collect.price_loader import download_prices


def _frame(start: date, n: int, close=100.0, adj_scale=1.0):
    idx = pd.to_datetime([start + timedelta(days=i) for i in range(n)])
    closes = [close] * n
    adjs = [close * adj_scale] * n
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Adj Close": adjs, "Volume": [1] * n}, index=idx)


def _seed(conn, ticker, start, n, close=100.0):
    conn.executemany("INSERT INTO prices VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                     [(ticker, start + timedelta(days=i), close, close, close, close, close) for i in range(n)])


@pytest.fixture
def conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def _fake(monkeypatch, frames):
    """frames: 호출 순서대로 돌려줄 DataFrame 리스트. 호출 인자 (ticker, start)를 기록한다."""
    calls = []

    def fake(ticker, start):
        calls.append((ticker, start))
        return frames.pop(0)

    monkeypatch.setattr(price_loader, "_yfinance_download", fake)
    return calls


def test_download_prices_fetches_from_overlap_window_when_history_exists(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)                          # 09-01 ~ 09-14 저장됨
    calls = _fake(monkeypatch, [_frame(date(2026, 9, 4), 17)])        # 09-04 ~ 09-20, 값 동일
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert calls == [("AAA", date(2026, 9, 4))]                        # 마지막 날 − 10일부터
    assert conn.execute("SELECT COUNT(*), MAX(date) FROM prices WHERE ticker = 'AAA'").fetchone() == (20, date(2026, 9, 20))


def test_download_prices_rescales_history_after_dividend_or_split(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    new = _frame(date(2026, 9, 4), 17, adj_scale=0.9)                 # 배당 조정: 겹치는 날의 Adj Close가 0.9배
    new.iloc[-1, new.columns.get_loc("Adj Close")] = float("nan")     # 마지막 날은 미확정 NaN
    calls = _fake(monkeypatch, [new])
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert len(calls) == 1                                             # 전체 재다운로드 없이
    hist = conn.execute("SELECT DISTINCT adj_close FROM prices WHERE ticker = 'AAA' AND date < DATE '2026-09-04'").fetchall()
    assert hist == [(pytest.approx(90.0),)]                           # 이전 이력이 같은 비율로 재스케일
    assert conn.execute("SELECT DISTINCT close FROM prices WHERE ticker = 'AAA'").fetchall() == [(100.0,)]


def test_download_prices_refetches_everything_when_overlap_disagrees(conn, monkeypatch):
    _seed(conn, "AAA", date(2026, 9, 1), 14)
    bad = _frame(date(2026, 9, 4), 17, adj_scale=0.9)
    bad.iloc[0, bad.columns.get_loc("Adj Close")] = 50.0               # 비율이 날마다 다름 → 조정이 아니라 데이터 수정
    full = _frame(date(2024, 1, 1), 5, close=7.0)
    calls = _fake(monkeypatch, [bad, full])
    download_prices(conn, ["AAA"], start=date(2024, 1, 1))
    assert calls[1] == ("AAA", date(2024, 1, 1))
    assert conn.execute("SELECT COUNT(*) FROM prices WHERE ticker = 'AAA' AND close = 7.0").fetchone()[0] == 5


def test_download_prices_uses_start_for_unknown_ticker(conn, monkeypatch):
    calls = _fake(monkeypatch, [_frame(date(2024, 1, 2), 3)])
    download_prices(conn, ["NEW"], start=date(2024, 1, 1))
    assert calls == [("NEW", date(2024, 1, 1))]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/collect/test_price_loader.py -q`
Expected: 첫 테스트가 `calls == [("AAA", date(2024, 1, 1))]`로 FAIL 등.

- [ ] **Step 3: 구현 — 종목별 알고리즘**

```
L = 저장된 마지막 날짜 (없으면 start부터 전체 받고 upsert → 끝)
df = _yfinance_download(t, L - OVERLAP_DAYS)  (실패 시 Stooq, 둘 다 실패면 failed)
overlap = df의 날짜 중 DB에도 있는 날짜 (Close·Adj Close가 NaN이 아닌 행만)
if overlap 없음 → upsert(df) → 끝
d* = overlap의 마지막 날
r_adj = df.adj_close[d*] / db.adj_close[d*];  r_close = df.close[d*] / db.close[d*]
if |r_adj − 1| ≤ ADJ_TOLERANCE and |r_close − 1| ≤ ADJ_TOLERANCE → upsert(df) → 끝
if 모든 overlap 날짜에서 |df.adj/(db.adj × r_adj) − 1| ≤ ADJ_TOLERANCE and |df.close/(db.close × r_close) − 1| ≤ ADJ_TOLERANCE:
    UPDATE prices SET adj_close = adj_close * r_adj,
                      open = open * r_close, high = high * r_close, low = low * r_close, close = close * r_close
    WHERE ticker = t AND date < df의 첫 날짜
    upsert(df) → 끝                                   -- 배당·분할의 소급 조정은 상수 배율이라 이력 전체에 같은 비율
else:
    df = _yfinance_download(t, start) (Stooq fallback 동일) → upsert(df)   -- 데이터 정정은 전체 재다운로드
```
`_upsert_prices`의 `ON CONFLICT … DO UPDATE`가 겹치는 행을 새 값으로 덮는다. 재스케일·전체 재다운로드는 `logger.info`로 남긴다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/unit -q`
Expected: 모두 PASS.

- [ ] **Step 5: 문서 갱신 후 Commit**

WORKFLOWS 1번: "가격 단계는 종목별 마지막 저장일 10일 전부터만 받고, 배당·분할 조정은 이력을 같은 비율로 재스케일한다(전체 재다운로드는 데이터가 정정된 종목만). HTTP 요청 수는 그대로라 2시간 → 약 30~40분으로 보면 된다(Task 2.9 배치 다운로드 뒤 다시 측정)."

```bash
git add src/thirteen_f/collect/price_loader.py tests/unit/collect/test_price_loader.py _claude_docs/WORKFLOWS.md _claude_docs/TROUBLESHOOTING.md
git commit -m "perf(collect): download prices incrementally and rescale history on adjustments"
```

### Task 1.8: 2026Q3 반영 + 재스윕 (운영, 2026-11-17 이후)

**Files:**
- Modify: `README.md`(Progress Status에 2026Q3 항목, Backtest Snapshot 표), `CLAUDE.md:42`(테스트 건수)
- Create: `docs/backtest-resweep-2026-11.md` (재스윕 결과 요약 — 상위 15·고원 판정·결정)
- (결정에 따라) Modify: `src/thirteen_f/backtest/runner.py:default_suite`, `README.md` 표

**Interfaces:**
- Consumes: Task 1.1~1.7 전부 (`main`에 커밋돼 있어야 한다), `.env`의 `SEC_USER_AGENT`, 인터넷.

- [ ] **Step 1: 시점·사전 조건 확인**

Run: `Get-Date; Test-Path .env; git status --short --untracked-files=no`
Expected: 2026-11-17 이후, `True`, 빈 status. 11-17 전이면 멈춘다 — 매니저 전원분이 아직 없다.

- [ ] **Step 2: 수집·분석 (자동 백업 포함)**

Run: `uv run thirteen-f update --skip-backtest --skip-export --skip-report`
Expected: 출력에 `backup: data\backups\13f-…duckdb`, `$ collect --start 2024Q1`, 끝에 `OK: {… 'value_unit_fixed': N}`(N ≥ 2: Baupost·Duquesne 전 분기). 가격 단계 로그에 rescale/full refetch 건수.

- [ ] **Step 3: 데이터 검증 (read-only)**

아래 세 쿼리를 scratchpad의 임시 `.py`(`duckdb.connect('data/13f.duckdb', read_only=True)`)로 실행한다 — PowerShell 한 줄에 따옴표를 겹치면 깨진다.

```sql
SELECT COUNT(DISTINCT cik) FROM filings
 WHERE period_of_report = DATE '2026-09-30' AND form_type = '13F-HR';           -- (1)
SELECT change_type, COUNT(*) FROM signals_quarterly GROUP BY 1 ORDER BY 1;       -- (2)
SELECT m.label, ROUND(SUM(h.value_usd) / 1e9, 1) AS bn
  FROM holdings h JOIN filings f USING (accession_no) JOIN managers m USING (cik)
 WHERE f.period_of_report = DATE '2026-09-30' AND f.superseded_by IS NULL
 GROUP BY 1 ORDER BY 1;                                                          -- (3)
```
Expected: (1) `13`(Burry 제외 전원; 적으면 하루 뒤 Step 2 재실행), (2) `exit` 행 수 > 0, (3) Druckenmiller·Klarman 총액이 수십억 달러 단위(0.0이 아님).

- [ ] **Step 4: 섹터 backfill → 백테스트 → export**

Run: `uv run python scripts/supplement_sector.py; uv run thirteen-f update --skip-collect --skip-report`
Expected: `update` 출력에 8전략의 CAGR/MDD/Sharpe, `OK Exported`. (Quarto가 없어 `--skip-report`.)

- [ ] **Step 5: 목표 비중 검증**

Run: `uv run thirteen-f targets --strategy ConsensusTopK`
Expected: SPY·IWM·EWY·RSP 없음, GOOG와 GOOGL이 동시에 없음, 종목 수 10.

- [ ] **Step 6: 재스윕 (DB 사본에서)**

Run: `uv run python scripts/sweep_backtests.py --start 2024-05-13 --end <prices 마지막 날> --split 2025-08-14`
Expected: `data/sweep/sweep_results.csv`. 판정 규칙([[backtest-strategy-comparison-fairness]] §4): 평균 보유 8종목 이상 중 Calmar 1위가 이웃 파라미터(한 축 한 칸)와 함께 고원을 이루는지, 1위가 이웃보다 크게 앞서면 과적합 신호. 결과와 판정을 `docs/backtest-resweep-2026-11.md`에 적는다.

- [ ] **Step 7: 기본 스위트 변경 여부는 사용자 결정**

1위 계열·파라미터가 바뀌었으면 사용자에게 표를 보여 주고, 승인 시 `runner.default_suite`와 README 표를 갱신한 뒤 `uv run thirteen-f backtest --all --start 2024-01-02; uv run thirteen-f export`를 다시 돈다.

- [ ] **Step 8: 문서 갱신 후 Commit**

README Progress Status에 "2026Q3 반영 (2026-11-xx) — 13명 수집, exit 시그널 복구·분모·단위 보정·ETF 제외/발행사 합산 적용 후 재스윕" 항목과 새 Backtest Snapshot 표(실행 기간·cost_bps 명시). CLAUDE.md 42줄의 테스트 건수를 실제 값으로.

```bash
git add README.md CLAUDE.md docs/backtest-resweep-2026-11.md
git commit -m "docs: record the 2026Q3 update and the November re-sweep"
```

### Phase 1 DoD

- `uv run pytest tests/unit -q` 전부 PASS; `uv run ruff check <수정 파일>` 위반 증가 없음.
- Task 1.8 Step 3·5의 검증값 충족; `data/backups/`에 백업 존재(Drive에도 반영); Plan 탭 목표 비중에 ETF·중복 클래스 없음.
- 재스윕 결과 문서화, 기본 스위트 변경 여부 결정.
- 사용자가 `/brain`으로 [[13f-tracker-overview]] 미결 목록(복수 클래스·ETF·천 달러·update 범위·자동 시작)을 갱신한다.
- 멈추고 사용자 승인을 받은 뒤 Phase 2로.

---

# Phase 2 — 품질·위생

목표: CI로 회귀를 막고, SPA에서 backend와 어긋나는 가짜 계산(브라우저 시뮬·보간 가격)을 없애고, 죽은 코드·의존성·문서 수치를 정리한다. 순서는 2.1 → 2.2(ruff 0이어야 CI가 켜진다) → 나머지는 독립.

### Task 2.1: ruff 기준선 0

**Files:**
- Modify: `src/**`, `tests/**`, `scripts/**` 중 ruff 위반 파일 (2026-10-31 기준 107건: E501 53, I001 26, F401 10, UP035 6, B905 5, E402 2, F541 2, B904 1, F841 1, UP037 1)
- Modify: `_claude_docs/TROUBLESHOOTING.md`(ruff·mypy 기준선 항목 → "ruff 0건을 CI가 강제")

- [ ] **Step 1: 자동 수정**

Run: `uv run ruff check --fix src tests scripts`
Expected: `Found 107 errors (45 fixed, 62 remaining).`

- [ ] **Step 2: 수동 수정**

E501은 줄바꿈(문자열은 인접 리터럴로 분리), B905는 길이가 같음이 보장되면 `strict=True`, 아니면 `strict=False`를 명시, E402(`collect/edgar_client.py`의 `from datetime import date` 중간 import)는 파일 상단으로, B904는 `raise … from exc`, F841은 변수 삭제. 동작을 바꾸지 않는다.

- [ ] **Step 3: 확인**

Run: `uv run ruff check src tests scripts; uv run pytest tests/unit -q`
Expected: `All checks passed!`, 모두 PASS.

- [ ] **Step 4: Commit**

```bash
git add -u src tests scripts
git add _claude_docs/TROUBLESHOOTING.md
git commit -m "style: clear the ruff baseline"
```
(`-u`는 이미 추적 중인 파일의 변경만 올린다 — 미추적 파일이 딸려 오지 않는다.)

### Task 2.2: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`(Progress Status 아래 "CI: GitHub Actions — ruff + unit (3.12·3.14)" 한 줄)

**Interfaces:**
- Produces: `main` push·PR마다 ubuntu-latest에서 Python 3.12·3.14 매트릭스로 `uv sync --frozen` → `ruff check src tests scripts` → `pytest tests/unit -q`. integration은 제외(네트워크·VCR).

- [ ] **Step 1: 워크플로 작성**

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.12", "3.14"]
    env:
      SEC_USER_AGENT: "ci test@example.com"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: ${{ matrix.python }}
      - run: uv sync --frozen
      - run: uv run ruff check src tests scripts
      - run: uv run pytest tests/unit -q
```

- [ ] **Step 2: 로컬 선검증**

Run: `uv run ruff check src tests scripts; uv run pytest tests/unit -q`
Expected: 통과. (Linux 전용 실패는 첫 CI 실행에서 드러난다 — 경로 구분자·인코딩이면 그 테스트만 고친다.)

- [ ] **Step 3: Commit, 사용자 확인 후 push**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: run ruff and unit tests on GitHub Actions"
git push origin main   # 사용자 확인 후
```
Expected: GitHub Actions `ci` 두 잡 모두 녹색. 실패하면 로그의 테스트 이름으로 고치고 다시 push.

### Task 2.3: Backtest 화면을 backend run 전용으로 (브라우저 시뮬 제거)

**Files:**
- Modify: `src/thirteen_f/web/static/hf-data.js` (188~453행 전략 라이브러리·`runStrategy`·`followStrategyEquity` 삭제, `STRATEGY_TYPES`는 `type/name/desc/color`만 남기고 `params`·`summary`·`makeDefaultStrategyParams`·`strategyLabel` 삭제, 하단 `Object.assign(window, …)` 목록 정리)
- Modify: `src/thirteen_f/web/static/hf-backtest.jsx` (`BacktestScreen` 상태·결과 계산, `StrategyEditor`·`ParamEditor` 삭제)
- Modify: `src/thirteen_f/web/static/hf-misc.jsx` (죽은 `scriptedReply` 187~약 330행과 window export 삭제 — `followStrategyEquity`의 유일한 호출자)
- Modify: `src/thirteen_f/web/exporter.py:export_backtest` (`"costBps": cost_bps` 추가), `tests/unit/web/test_exporter.py::test_export_backtest_writes_runs_with_holdings_and_metrics` (+ `costBps` 단언)
- Modify: `_claude_docs/FRONTEND_PARITY.md`(`runStrategy` 행 삭제, 원칙 4 삭제), `_claude_docs/TROUBLESHOOTING.md`("Backtest 화면에 SIM 배지" 항목 삭제), `README.md:10`(Backtest 설명에 "backend run만 표시")

**Interfaces:**
- Consumes: `BACKTESTS[]` = `backtest.json` (`created_at DESC` 정렬, 항목 `{run_id, name, params, equity, dd, qrets, benchEquity, holdingsLog, metrics, costBps}`).
- Produces (화면 동작):
  - 칩 = 전략 이름(`name`)별 최신 run 하나씩(배열에서 이름별 첫 항목), 전부 `on`, 색은 `nextColor` 팔레트 순서. 칩 라벨은 `run.name` 그대로(`ConsensusTopK(3,10)`), `type`은 `name.split("(")[0]`.
  - `results`는 on 칩의 run 데이터만. **fallback 없음**. `_source`·`simCount`·SIM 배지·"+ add strategy" 피커·QUICK CONTROLS·"Strategy editor" 섹션 삭제.
  - 비용 표시 `${costBps} bps · backend run`(첫 run의 `costBps`), 벤치마크 라벨 "S&P 500 (SPY)", STRATEGIES 스탯 sub "backend runs".
  - Metrics 표에서 backend가 주지 않는 VOL·β·TURN 열과 lead 섹션의 BETA·VOL·TURNOVER 스탯 삭제; 대신 lead 섹션에 `COST` 스탯(`${costBps} bp 편도`).
  - Builder·Ask·Plan 화면은 바뀌지 않는다(`quarterActivity` 등 파생 helper는 유지).

- [ ] **Step 1: exporter 테스트 추가 → 실패 확인**

`test_export_backtest_writes_runs_with_holdings_and_metrics`에 `assert run["costBps"] == 10.0` 추가 (fixture의 `backtest_runs` INSERT가 `cost_bps` 10.0을 넣는다).
Run: `uv run pytest tests/unit/web/test_exporter.py -q` → FAIL(KeyError).

- [ ] **Step 2: exporter 구현 → 통과**

`export_backtest`의 SELECT에 `r.cost_bps`를 넣고 payload에 `"costBps": cost_bps`.
Run: `uv run pytest tests/unit -q` → PASS.

- [ ] **Step 3: SPA 수정** (위 Produces대로)

- [ ] **Step 4: 브라우저 확인**

Run: `uv run thirteen-f serve` → `http://127.0.0.1:8765/#/backtest`
Expected: 칩 8개(기본 스위트 run 이름), SIM 문구 없음, 표에 VOL/β/TURN 없음, 콘솔 에러 0. `#/ask`·`#/builder`·`#/plan`도 렌더된다. `grep -n "runStrategy\|pickByType\|followStrategyEquity\|scriptedReply\|_source" src/thirteen_f/web/static/*` → 0건.

- [ ] **Step 5: 문서 갱신 후 Commit**

```bash
git add src/thirteen_f/web/static/hf-data.js src/thirteen_f/web/static/hf-backtest.jsx src/thirteen_f/web/static/hf-misc.jsx src/thirteen_f/web/exporter.py tests/unit/web/test_exporter.py _claude_docs/FRONTEND_PARITY.md _claude_docs/TROUBLESHOOTING.md README.md
git commit -m "refactor(web): show backend backtest runs only and drop the browser simulation"
```

### Task 2.4: 스파크라인·가격 차트를 실제 종가로

**Files:**
- Modify: `src/thirteen_f/web/exporter.py:export_stocks` (`pxw` 추가), `tests/unit/web/test_exporter.py` (+ 테스트)
- Modify: `src/thirteen_f/web/static/hf-data.js` (32~50행 `buildWeeklyPrices`와 600~606행 `pxWeekly` 생성 삭제, 8행 주석 갱신)
- Modify: `hf-dashboard.jsx:32,120`, `hf-misc.jsx:408,520`, `hf-stock.jsx:29,89,124-134`
- Modify: `_claude_docs/DATA_FORMATS.md:36`(stocks.json에 `pxw`), `_claude_docs/FRONTEND_PARITY.md`(`pxWeekly` 행 → `STOCKS[].pxw` backend)

**Interfaces:**
- Produces: `stocks.json` 항목에 `pxw: list[float]` — `MAX(prices.date)`로 끝나는 최근 12개 ISO 주의 주별 마지막 종가(`close`), 주가 적으면 짧게, 없으면 `[]`.
- SPA: 네 곳의 `Spark values={….pxWeekly.slice(-12)}` → `values={….pxw}`; 대시보드 spotlight 차트 `values: spot.stock.pxw`; 종목 상세의 가격 차트는 이미 받아 둔 `pxDaily.close`를 쓰고 x 라벨은 `pxDaily.date[i].slice(0, 7)`, 제목 "Price · daily close". `pxDaily.close.length < 2`면 차트 대신 `muted` 문구 "가격 데이터 없음".

- [ ] **Step 1: 실패하는 테스트 추가 — `tests/unit/web/test_exporter.py`**

```python
def test_export_stocks_includes_last_12_weekly_closes(conn, tmp_path: Path):
    """pxw = MAX(prices.date)로 끝나는 최근 12 ISO 주의 주별 마지막 종가. 보간·노이즈 없음."""
    conn.execute("INSERT INTO cusip_ticker_map (cusip, ticker, name, sector, is_etf) "
                 "VALUES ('594918104', 'MSFT', 'Microsoft', 'Technology', FALSE)")
    for i in range(100):   # 2024-03-23 ~ 2024-06-30, close = 1..100
        d = date(2024, 6, 30) - timedelta(days=99 - i)
        conn.execute("INSERT INTO prices (ticker, date, close, adj_close) VALUES ('MSFT', ?, ?, ?)", (d, float(i + 1), float(i + 1)))
    export_stocks(conn, tmp_path)
    stocks = {s["t"]: s for s in json.loads((tmp_path / "stocks.json").read_text(encoding="utf-8"))}
    msft = stocks["MSFT"]["pxw"]
    assert len(msft) == 12 and msft[-1] == 100.0 and msft == sorted(msft)
    assert msft[-2] == 93.0                      # 직전 ISO 주(06-17~06-23)의 마지막 날 06-23 = 93
    assert stocks["AAPL"]["pxw"] == [200.5]      # fixture의 06-28·06-30은 같은 ISO 주 → 1점
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/unit/web/test_exporter.py -q` → `KeyError: 'pxw'`.

- [ ] **Step 3: 구현**

```sql
WITH last AS (SELECT MAX(date) AS d FROM prices)
SELECT ticker, date_trunc('week', date) AS wk, MAX_BY(close, date) AS wclose
FROM prices, last
WHERE date > last.d - INTERVAL 91 DAY AND close IS NOT NULL
GROUP BY ticker, wk
ORDER BY ticker, wk
```
ticker별로 모아 마지막 12개만 `pxw`에 넣는다(한 번의 쿼리, 티커 루프 금지).

- [ ] **Step 4: 통과 확인 → SPA 수정 → 브라우저 확인**

Run: `uv run pytest tests/unit -q` → PASS. `uv run thirteen-f export` 후 `#/`, `#/stocks`, `#/stocks/AAPL`, `#/consensus`, `#/builder`에서 스파크라인·가격 차트 표시, 콘솔 에러 0. `grep -n "pxWeekly\|buildWeeklyPrices" src/thirteen_f/web/static/*` → 0건.

- [ ] **Step 5: 문서 갱신 후 Commit**

```bash
git add src/thirteen_f/web/exporter.py tests/unit/web/test_exporter.py src/thirteen_f/web/static/hf-data.js src/thirteen_f/web/static/hf-dashboard.jsx src/thirteen_f/web/static/hf-misc.jsx src/thirteen_f/web/static/hf-stock.jsx _claude_docs/DATA_FORMATS.md _claude_docs/FRONTEND_PARITY.md
git commit -m "fix(web): draw sparklines and price charts from real closes instead of interpolated noise"
```

### Task 2.5: Quarto 차트 분리, Streamlit 잔존물 삭제

**Files:**
- Move: `src/thirteen_f/_legacy_dashboard/charts.py` → `reports/quarto/_charts.py` (`git mv`; 어디서도 쓰지 않는 `portfolio_treemap` 삭제, 4개 함수 유지)
- Modify: `reports/quarto/01_overview.qmd:8`, `reports/quarto/04_backtest.qmd:8` (`from _charts import …`)
- Delete: `src/thirteen_f/_legacy_dashboard/` 나머지 전부, `.streamlit/config.toml` (`git rm -r`)
- Modify: `CLAUDE.md`(Architecture의 `_legacy_dashboard` 항목 → "`reports/quarto/_charts.py`는 Quarto 전용 plotly 차트"), `_claude_docs/ARCHITECTURE.md:37,71`, `README.md:95`, `_claude_docs/TROUBLESHOOTING.md`(mypy 기준선 설명에서 `_legacy_dashboard` 20건 문장 삭제), `.gitignore`("# Quarto / Streamlit" 주석 → "# Quarto")

- [ ] **Step 1: 이동·삭제·import 수정**

Run: `git mv src/thirteen_f/_legacy_dashboard/charts.py reports/quarto/_charts.py; git rm -r -q src/thirteen_f/_legacy_dashboard .streamlit`

- [ ] **Step 2: 확인**

Run: `uv run python -c "import sys; sys.path.insert(0, 'reports/quarto'); import _charts; print(sorted(n for n in dir(_charts) if not n.startswith('_') and callable(getattr(_charts, n)) and n[0].islower()))"`
Expected: `['change_waterfall', 'consensus_heatmap', 'cumulative_curve', 'drawdown_chart']`(pandas·plotly 모듈 이름은 제외).

Run: `uv run mypy src/thirteen_f | Select-String 'Found'` ; `uv run pytest tests/unit -q`
Expected: 오류 수 ≤ 18 (38 − `_legacy_dashboard` 20), 테스트 PASS. `grep -rn "_legacy_dashboard" --include=*.py --include=*.qmd --include=*.md . | grep -v docs/superpowers` → CLAUDE.md·README·ARCHITECTURE의 갱신된 문장만.
(Quarto CLI가 이 PC에 없어 `thirteen-f report`로는 확인하지 못한다 — 설치 뒤 `uv run thirteen-f report --latest`가 첫 검증이다.)

- [ ] **Step 3: Commit**

```bash
git add reports/quarto/_charts.py reports/quarto/01_overview.qmd reports/quarto/04_backtest.qmd CLAUDE.md _claude_docs/ARCHITECTURE.md README.md _claude_docs/TROUBLESHOOTING.md .gitignore
git commit -m "refactor(report): move the Quarto charts next to the qmd files and delete the Streamlit legacy"
```
(`git rm`·`git mv`로 stage된 삭제·이동은 이미 index에 있다.)

### Task 2.6: 의존성·일회성 파일 정리

**Files:**
- Modify: `pyproject.toml` (`polars` 삭제 — import하는 곳 없음; `jupyter`·`plotly`를 `[project.optional-dependencies] report = ["jupyter>=1.0", "plotly>=5.20"]`로 이동), `uv.lock`(`uv lock`)
- Modify: `src/thirteen_f/cli.py:report` (Quarto 검사 뒤 `importlib.util.find_spec("plotly") is None or find_spec("jupyter") is None` → `typer.echo("Quarto 의존성 미설치: uv sync --extra report", err=True); raise typer.Exit(2)`)
- Create: `tests/unit/test_cli_report.py`
- Delete: `config/analysis.toml`(읽는 코드 없음), `scripts/supplement.py`(2026-05 일회성)
- Modify: `README.md`(Setup에 `uv sync --extra report`, Tech Stack의 plotly 문구), `CLAUDE.md`(Commands `report` 줄에 "`uv sync --extra report` 필요"), `_claude_docs/DATA_FORMATS.md:53`(analysis.toml 항목 삭제), `_claude_docs/TROUBLESHOOTING.md`(`analysis.toml` 항목 삭제, `report` exit 2 항목에 extras 문구)

- [ ] **Step 1: 실패하는 테스트 — `tests/unit/test_cli_report.py`**

```python
import importlib.util
import shutil

from typer.testing import CliRunner

from thirteen_f.cli import app


def test_report_exits_2_when_quarto_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    r = CliRunner().invoke(app, ["report", "--latest"])
    assert r.exit_code == 2 and "winget" in r.output


def test_report_exits_2_when_report_extra_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: "C:/quarto/quarto.exe")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    r = CliRunner().invoke(app, ["report", "--latest"])
    assert r.exit_code == 2 and "--extra report" in r.output
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/unit/test_cli_report.py -q` → 두 번째 FAIL(exit 2가 아니거나 문구 없음).

- [ ] **Step 3: 구현 + 의존성 정리**

Run: `uv lock; uv sync --extra report` (개발 PC는 report extra 포함으로 동기화)
Expected: lock 갱신, `polars` 제거 확인 `uv pip list | Select-String polars` → 없음.

- [ ] **Step 4: 확인** — `uv run pytest tests/unit -q` PASS; `git rm config/analysis.toml scripts/supplement.py`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/thirteen_f/cli.py tests/unit/test_cli_report.py README.md CLAUDE.md _claude_docs/DATA_FORMATS.md _claude_docs/TROUBLESHOOTING.md
git commit -m "chore(deps): make the Quarto stack an optional extra, drop polars and one-off files"
```

### Task 2.7: React production 빌드 + 문서 수치 현행화

**Files:**
- Modify: `src/thirteen_f/web/static/index.html:16-17`
- Modify: `tests/unit/web/test_server.py:143`
- Modify: `CLAUDE.md:42`(회귀 기준 건수), `README.md:103`(테스트 건수), `_claude_docs/TROUBLESHOOTING.md`(기준선: ruff 0, mypy 실제 값)

**Interfaces:**
- index.html의 React 두 스크립트를 production 빌드로 바꾼다. SRI(2026-10-31 unpkg에서 계산):
  - `https://unpkg.com/react@18.3.1/umd/react.production.min.js` → `sha384-DGyLxAyjq0f9SPpVevD6IgztCFlnMF6oW/XQGmfe+IsZ8TqEiDrcHkMLKI6fiB/Z`
  - `https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js` → `sha384-gTGxhz21lVGYNMcdJOyq01Edg0jhn/c22nsx0kyqP0TxaV5WVdsSH1fSDUf5YJj1`
  - 재검증: `curl.exe -sL <url> | openssl dgst -sha384 -binary | openssl base64 -A` (Git Bash). Babel standalone은 그대로.

- [ ] **Step 1: 테스트 수정 → 실패 확인**

`test_index_html_versions_local_asset_urls`의 단언을 `'unpkg.com/react@18.3.1/umd/react.production.min.js"' in body`로.
Run: `uv run pytest tests/unit/web/test_server.py -q` → FAIL.

- [ ] **Step 2: index.html 수정 → 통과 → 브라우저 확인**

Run: `uv run pytest tests/unit -q` → PASS. 브라우저 `#/`에서 콘솔에 "development build" 경고가 없고 화면이 뜬다.

- [ ] **Step 3: 문서 수치**

Run: `uv run pytest tests/unit -q | Select-String passed; uv run ruff check src tests scripts; uv run mypy src/thirteen_f | Select-String Found`
그 값을 CLAUDE.md 42줄("회귀 기준: N건"), README 103줄, TROUBLESHOOTING 기준선 항목에 적는다.

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/static/index.html tests/unit/web/test_server.py CLAUDE.md README.md _claude_docs/TROUBLESHOOTING.md
git commit -m "chore(web): load React production builds; refresh documented test and lint counts"
```

### Task 2.8: continuity 점수를 SQL 한 번으로

**Files:**
- Modify: `src/thirteen_f/analyze/continuity.py:26-61` (`update_continuity_scores`)
- Modify: `tests/unit/analyze/test_continuity.py` (+ SQL 경로 테스트)

**Interfaces:**
- Produces: `update_continuity_scores(conn) -> int` — 시그니처·반환(갱신 행 수) 유지, Python 루프·`executemany` 대신 `LAG` 3개 + CASE로 한 번의 `UPDATE`. `continuity_from_changes`는 참조 구현으로 남긴다(테스트가 둘을 비교).

- [ ] **Step 1: 실패하는 테스트 추가**

```python
from datetime import date

import duckdb

from scripts.init_db import init_db
from thirteen_f.analyze.continuity import update_continuity_scores

QS = [date(2023, 3, 31), date(2023, 6, 30), date(2023, 9, 30), date(2023, 12, 31), date(2024, 3, 31)]


def test_sql_update_matches_reference_function(tmp_path):
    seqs = {"A": ["new", "increase", "decrease", "hold"],
            "B": ["hold", "exit", "new"],
            "C": ["new", "increase", "hold", "hold", "hold"]}
    db = tmp_path / "t.duckdb"
    init_db(db)
    c = duckdb.connect(str(db))
    for cusip, seq in seqs.items():
        for i, ch in enumerate(seq):
            c.execute("INSERT INTO signals_quarterly (cik, cusip, period_of_report, change_type) VALUES ('m', ?, ?, ?)",
                      (cusip, QS[i], ch))
    assert update_continuity_scores(c) == 12
    for cusip, seq in seqs.items():
        for i in range(len(seq)):
            got = c.execute("SELECT continuity_score FROM signals_quarterly WHERE cusip = ? AND period_of_report = ?",
                            (cusip, QS[i])).fetchone()[0]
            assert got == pytest.approx(continuity_from_changes(seq[: i + 1])), (cusip, i)
    c.close()
```

- [ ] **Step 2: 실패 확인** — 현재 구현은 통과할 수 있다(동작 동일). 그래도 실행해 기준을 잡는다: `uv run pytest tests/unit/analyze/test_continuity.py -q`.

- [ ] **Step 3: 구현**

```sql
UPDATE signals_quarterly s
SET continuity_score = w.score
FROM (
    SELECT cik, cusip, period_of_report,
           (CASE WHEN c0 IN ('decrease', 'exit') THEN 0
                 WHEN c1 IS NULL OR c1 IN ('decrease', 'exit') THEN 1
                 WHEN c2 IS NULL OR c2 IN ('decrease', 'exit') THEN 2
                 WHEN c3 IS NULL OR c3 IN ('decrease', 'exit') THEN 3
                 ELSE 4 END) / 4.0 AS score
    FROM (
        SELECT cik, cusip, period_of_report, change_type AS c0,
               LAG(change_type, 1) OVER w AS c1,
               LAG(change_type, 2) OVER w AS c2,
               LAG(change_type, 3) OVER w AS c3
        FROM signals_quarterly
        WINDOW w AS (PARTITION BY cik, cusip ORDER BY period_of_report)
    )
) w
WHERE s.cik = w.cik AND s.cusip = w.cusip AND s.period_of_report = w.period_of_report
```
반환값은 `SELECT COUNT(*) FROM signals_quarterly`.

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/unit -q` PASS. 실데이터 소요 시간은 Task 1.8 이후 `analyze` 로그로 확인(기존 약 39초 → 1초 미만 기대).

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/analyze/continuity.py tests/unit/analyze/test_continuity.py
git commit -m "perf(analyze): compute continuity scores in a single SQL update"
```

### Task 2.9: 가격 배치 다운로드

**Files:**
- Modify: `src/thirteen_f/collect/price_loader.py` (`_yf_batch`, `download_prices` 내부 그룹화)
- Modify: `tests/unit/collect/test_price_loader.py`
- Modify: `_claude_docs/WORKFLOWS.md`(소요 시간 문장 — 실측 후)

**Interfaces:**
- Produces: `BATCH_SIZE = 50`, `_yf_batch(tickers: list[str], start: date) -> dict[str, pd.DataFrame]` — `yf.download(tickers, start=…, group_by="ticker", auto_adjust=False, threads=True, progress=False)` 결과를 ticker별 단일 레벨 컬럼 DataFrame으로 나눠 반환(전부 NaN인 ticker는 제외). `download_prices`는 Task 1.7의 종목별 fetch 시작일이 같은 ticker들을 50개씩 묶어 `_yf_batch`로 받고, 배치 결과에 없는 ticker만 기존 단일 경로(`_yfinance_download` → Stooq)로 처리한다. Task 1.7의 overlap·재스케일 로직은 종목별로 그대로 적용.

- [ ] **Step 1: 실패하는 테스트 추가**

```python
def test_download_prices_batches_tickers_with_the_same_start(conn, monkeypatch):
    batch_calls = []

    def fake_batch(tickers, start):
        batch_calls.append((tuple(tickers), start))
        return {t: _frame(date(2024, 1, 2), 3) for t in tickers if t != "MISSING"}

    single_calls = []

    def fake_single(ticker, start):
        single_calls.append((ticker, start))
        return _frame(date(2024, 1, 2), 3)

    monkeypatch.setattr(price_loader, "_yf_batch", fake_batch)
    monkeypatch.setattr(price_loader, "_yfinance_download", fake_single)
    download_prices(conn, ["AAA", "BBB", "MISSING"], start=date(2024, 1, 1))
    assert batch_calls == [(("AAA", "BBB", "MISSING"), date(2024, 1, 1))]
    assert single_calls == [("MISSING", date(2024, 1, 1))]        # 배치에 빠진 종목만 단일 경로
    assert conn.execute("SELECT COUNT(DISTINCT ticker) FROM prices").fetchone()[0] == 3
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/unit/collect/test_price_loader.py -q` → `AttributeError: _yf_batch`.

- [ ] **Step 3: 구현 → 통과 확인** — `uv run pytest tests/unit -q` PASS. Task 1.7의 네 테스트는 `_yf_batch`를 patch하지 않으므로, 배치 호출이 실패하면(실제 yfinance가 없는 환경 등) 단일 경로로 넘어가야 통과한다 — 즉 `_yf_batch` 예외·빈 결과는 단일 경로 fallback.

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/collect/price_loader.py tests/unit/collect/test_price_loader.py _claude_docs/WORKFLOWS.md
git commit -m "perf(collect): fetch prices in batches of 50 tickers"
```

### Phase 2 DoD

- `uv run ruff check src tests scripts` 통과, CI 두 잡 녹색(push 승인 시), `uv run pytest tests/unit -q` PASS, mypy ≤ 18.
- 브라우저: `#/backtest` SIM 없음·칩 8개, 스파크라인·가격 차트가 실제 종가, React dev 경고 없음, 콘솔 에러 0.
- `grep -rn "_legacy_dashboard\|pxWeekly\|runStrategy\|analysis.toml" src reports CLAUDE.md _claude_docs` → 0건.
- 멈추고 사용자 승인을 받은 뒤 Phase 3로.

---

# Phase 3 — 강화

목표: 매분기 손으로 하던 일(공시 확인·기한 계산)을 자동화하고, 상장폐지·인수된 종목이 매매 목록에 섞이지 않게 한다. 세 Task는 서로 독립이다.

### Task 3.1: 13F 기한에 미국 연방 공휴일 반영

**Files:**
- Modify: `src/thirteen_f/core/dates.py` (+ `us_federal_holidays`, `sec_13f_deadline`)
- Modify: `src/thirteen_f/web/exporter.py:374-381` (`_next_rebalance`가 `sec_13f_deadline(quarter_end(다음 분기))` 반환)
- Modify: `tests/unit/test_dates.py`, `tests/unit/web/test_exporter_targets.py:151-154`
- Modify: `src/thirteen_f/web/static/hf-plan.jsx:92` (sub "분기말 + 45일 (예상)" → "분기말 + 45일, 주말·연방 공휴일 다음 영업일"), `_claude_docs/DATA_FORMATS.md`(targets.json `next_rebalance` 설명)

**Interfaces:**
- Produces (`core/dates.py`):
  - `us_federal_holidays(year: int) -> set[date]` — New Year's(1/1), MLK(1월 3번째 월), Presidents'(2월 3번째 월), Memorial(5월 마지막 월), Juneteenth(6/19), Independence(7/4), Labor(9월 첫 월), Columbus(10월 2번째 월), Veterans(11/11), Thanksgiving(11월 4번째 목), Christmas(12/25). 고정일이 토요일이면 금요일, 일요일이면 월요일로 관측. 외부 패키지 없이 구현.
  - `sec_13f_deadline(period_end: date) -> date` — `period_end + 45일`을 토·일·공휴일이 아닌 날까지 하루씩 미룬다.

- [ ] **Step 1: 실패하는 테스트 — `tests/unit/test_dates.py`**

```python
from thirteen_f.core.dates import sec_13f_deadline, us_federal_holidays


def test_us_federal_holidays_2026_observed_dates():
    h = us_federal_holidays(2026)
    assert date(2026, 1, 19) in h       # MLK — 1월 3번째 월요일
    assert date(2026, 2, 16) in h       # Presidents' Day
    assert date(2026, 7, 3) in h        # 7/4이 토요일 → 금요일 관측
    assert date(2026, 11, 26) in h      # Thanksgiving — 11월 4번째 목요일
    assert date(2026, 12, 25) in h


def test_sec_13f_deadline_rolls_past_weekends_and_holidays():
    assert sec_13f_deadline(date(2025, 12, 31)) == date(2026, 2, 17)   # 2/14 토 → 2/16 월 Presidents' Day → 2/17
    assert sec_13f_deadline(date(2026, 6, 30)) == date(2026, 11, 16)   # 11/14 토 → 월
    assert sec_13f_deadline(date(2024, 6, 30)) == date(2024, 11, 14)   # 목요일 그대로
    assert sec_13f_deadline(date(2024, 12, 31)) == date(2025, 2, 14)   # 금요일, Presidents' Day는 2/17
```

`tests/unit/web/test_exporter_targets.py::test_next_rebalance_rolls_weekend_deadline_to_monday`에 `assert _next_rebalance(date(2025, 9, 30)) == date(2026, 2, 17)` 추가.

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/unit/test_dates.py tests/unit/web/test_exporter_targets.py -q` → ImportError / `2026-02-16`.

- [ ] **Step 3: 구현 → 통과 확인** — `uv run pytest tests/unit -q` PASS.

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/core/dates.py src/thirteen_f/web/exporter.py tests/unit/test_dates.py tests/unit/web/test_exporter_targets.py src/thirteen_f/web/static/hf-plan.jsx _claude_docs/DATA_FORMATS.md
git commit -m "fix(web): roll the 13F deadline past US federal holidays"
```

### Task 3.2: 새 13F-HR 감지기 `check-filings` + 일일 자동 갱신 스크립트

**Files:**
- Create: `src/thirteen_f/collect/watch.py`
- Modify: `src/thirteen_f/cli.py` (`check_filings` 명령, 이름 `check-filings`)
- Create: `tests/unit/collect/test_watch.py`, `tests/unit/test_cli_check_filings.py`
- Create: `scripts/check_and_update.ps1`
- Modify: `_claude_docs/WORKFLOWS.md`("새 분기 13F 반영" 앞에 "0. `check-filings`로 새 공시 확인 / 자동화" + 스케줄러 등록·해제 명령), `README.md`(CLI 표에 `check-filings`), `CLAUDE.md`(Commands에 한 줄)

**Interfaces:**
- Produces (`collect/watch.py`): `find_new_filings(conn, client, managers: list[dict]) -> list[dict]` — 매니저마다 `[cik, *extra_ciks]`의 `client.get_submissions(filer_cik)`를 `extract_13f_filings`로 걸러 **`form_type == "13F-HR"`**(원본만; 정정본은 뒤따르는 collect가 처리)이고 `period_of_report >= DB 최소 분기`(DB가 비면 전부)이며 `accession_no`가 `filings`에 없는 것을 `{"label", "filer_cik", "accession_no", "period_of_report", "filed_at"}`로 반환, `filed_at` 오름차순.
- Produces (CLI): `thirteen-f check-filings` — `config/managers.yaml`을 읽고 read-only 연결로 위 함수를 호출, 한 줄씩 `label  period  filed_at  accession` 출력. 새 공시가 있으면 exit code **1**, 없으면 `새 13F-HR 없음`과 exit 0. (`load_settings()` 필요 — SEC_USER_AGENT.)
- Produces (`scripts/check_and_update.ps1`): 저장소 루트로 이동 → `scripts\py.ps1 -m thirteen_f.cli check-filings`; exit 1이면 `scripts\py.ps1 -m thirteen_f.cli update --skip-report` → `scripts\py.ps1 scripts/supplement_sector.py` → `scripts\py.ps1 -m thirteen_f.cli export`. 출력은 `data/logs/check_and_update.log`에 날짜와 함께 append.
- Consumes: `tests/fixtures/edgar/submissions_buffett.json`(13F-HR 2건 + 13F-HR/A 1건), `EdgarClient.get_submissions`, `extract_13f_filings`.

- [ ] **Step 1: 실패하는 테스트 — `tests/unit/collect/test_watch.py`**

```python
import json
from pathlib import Path

import duckdb

from scripts.init_db import init_db
from thirteen_f.collect.watch import find_new_filings

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "edgar" / "submissions_buffett.json"


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_submissions(self, cik):
        self.calls.append(cik)
        return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _conn(tmp_path):
    db = tmp_path / "t.duckdb"
    init_db(db)
    return duckdb.connect(str(db))


def test_reports_only_original_13f_hr_not_in_db(tmp_path):
    c = _conn(tmp_path)
    managers = [{"label": "Buffett", "cik": "0001067983", "extra_ciks": ["0002026053"]}]
    client = FakeClient()
    new = find_new_filings(c, client, managers)
    assert client.calls == ["0001067983", "0002026053"]
    assert all(n["label"] == "Buffett" for n in new)
    accs = {n["accession_no"] for n in new}
    assert accs == {"0001067983-24-000017", "0001067983-24-000015"}   # 13F-HR 원본 2건, 13F-HR/A(…16)·10-K 제외
    assert len(new) == 4                                               # 두 CIK가 같은 fixture를 돌려주므로 2 × 2
    assert [n["filed_at"] for n in new] == sorted(n["filed_at"] for n in new)


def test_filings_already_in_db_are_skipped(tmp_path):
    c = _conn(tmp_path)
    c.execute("INSERT INTO managers (cik, name) VALUES ('0001067983', 'B')")
    c.execute("INSERT INTO filings VALUES ('0001067983-24-000017', '0001067983', '13F-HR', DATE '2024-03-31', DATE '2024-05-15', FALSE, NULL)")
    new = find_new_filings(c, FakeClient(), [{"label": "Buffett", "cik": "0001067983"}])
    assert [n["accession_no"] for n in new] != [] and "0001067983-24-000017" not in [n["accession_no"] for n in new]
```

`tests/unit/test_cli_check_filings.py`: `monkeypatch.setattr("thirteen_f.collect.watch.find_new_filings", lambda *a, **k: [...])`로 결과를 주입해 (a) 비면 exit 0·`없음` 출력, (b) 1건이면 exit 1·accession 포함을 단언 (`EdgarClient`는 `monkeypatch.setattr("thirteen_f.cli.EdgarClient", FakeClient)`처럼 생성자 호출을 가로막는다 — cli가 `from thirteen_f.collect.edgar_client import EdgarClient`를 함수 안에서 하므로 `thirteen_f.collect.edgar_client.EdgarClient`를 patch한다). 환경 변수는 `test_cli_targets.py`의 `_env` fixture 방식.

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/unit/collect/test_watch.py tests/unit/test_cli_check_filings.py -q` → ModuleNotFoundError.

- [ ] **Step 3: 구현 (`watch.py`, CLI, `check_and_update.ps1`) → 통과 확인** — `uv run pytest tests/unit -q` PASS.

- [ ] **Step 4: 실환경 확인 (네트워크)**

Run: `uv run thirteen-f check-filings; echo $LASTEXITCODE`
Expected: 2026-11-17 이전이면 Q3 13F-HR들이 나열되고 1, 이후 collect를 마친 상태면 `없음`과 0.

- [ ] **Step 5: 스케줄러 등록 (사용자 확인 후) + 문서**

```powershell
$root = (Get-Location).Path
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $root `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$root\scripts\check_and_update.ps1`""
Register-ScheduledTask -TaskName "13f-check-filings" -Action $action -Trigger (New-ScheduledTaskTrigger -Daily -At 8am)
```
WORKFLOWS에 등록·해제·로그 위치를 적는다.

- [ ] **Step 6: Commit**

```bash
git add src/thirteen_f/collect/watch.py src/thirteen_f/cli.py tests/unit/collect/test_watch.py tests/unit/test_cli_check_filings.py scripts/check_and_update.ps1 _claude_docs/WORKFLOWS.md README.md CLAUDE.md
git commit -m "feat(cli): add check-filings to detect new 13F-HR filings and a daily update script"
```

### Task 3.3: 가격이 끊긴(상장폐지·인수) 종목 처리

**Files:**
- Modify: `src/thirteen_f/web/exporter.py` (`STALE_DAYS = 10`, `_stale_tickers(conn) -> set[str]`, `describe()`에 `"priceStale"`)
- Modify: `src/thirteen_f/backtest/engine.py:85-89` (리밸런스 시 stale 종목 제외·재정규화)
- Modify: `tests/unit/web/test_exporter_targets.py`, `tests/unit/backtest/test_engine.py`
- Modify: `src/thirteen_f/web/static/hf-plan.jsx` (티커 옆 `STALE` 배지, "실행 전 확인"에 stale 목록 항목)
- Modify: `_claude_docs/TROUBLESHOOTING.md`("가격이 어느 날짜에서 끊김" ② 문장 갱신), `_claude_docs/DATA_FORMATS.md`(targets.json에 `priceStale`), `_claude_docs/FRONTEND_PARITY.md`(TARGETS 행)

**Interfaces:**
- Produces (exporter): `priceStale: bool` — 그 ticker의 `MAX(prices.date)`가 `MAX(prices.date) over all − STALE_DAYS`보다 이르거나 가격이 없으면 `True`. positions·sells 양쪽 항목에 들어간다.
- Produces (engine): 영업일 `d`에 `target`을 받은 뒤, `prices`에서 `date <= d`인 마지막 날짜가 `d − STALE_DAYS`보다 이른 ticker를 `target`에서 빼고 남은 비중을 합 1로 재정규화한다(빈 dict면 그대로 현금). 조회는 `SELECT ticker, MAX(date) FROM prices WHERE ticker IN (…) AND date <= ? GROUP BY ticker` 하루 한 번.
- Plan 탭: `r.priceStale`이면 `<span className="hf-badge sm plan-etf">STALE</span>`; 주의사항에 `<li>` "가격이 {STALE_DAYS}일 넘게 없는 종목: … — 상장폐지·인수 가능성, 매수 대상에서 빼고 확인하세요".

- [ ] **Step 1: 실패하는 테스트**

`tests/unit/web/test_exporter_targets.py`:
```python
def test_export_targets_flags_stale_prices_relative_to_market_last_date(conn, tmp_path: Path):
    """기준은 '오늘'이 아니라 prices의 마지막 날(08-30) — CCC는 07-01이 마지막이라 stale, AAA·BBB는 아니다."""
    conn.execute("INSERT INTO prices (ticker, date, close, adj_close) VALUES ('CCC', DATE '2024-07-01', 10.0, 10.0)")
    export_targets(conn, tmp_path, as_of=date(2024, 10, 15))
    cons = _by_name(_load(tmp_path), "ConsensusTopK(3,10)")
    assert {p["ticker"]: p["priceStale"] for p in cons["positions"]} == {"AAA": False, "BBB": False}
    assert cons["sells"][0]["ticker"] == "CCC" and cons["sells"][0]["priceStale"] is True
```

`tests/unit/backtest/test_engine.py`:
```python
def test_engine_drops_tickers_whose_prices_stopped(conn):
    """MSFT 가격이 2024-06-30에 끊기면 10일 뒤부터 포지션에서 빠지고 비중은 AAPL 100%가 된다."""
    conn.execute("DELETE FROM prices WHERE ticker = 'MSFT' AND date > DATE '2024-06-30'")
    result = run_backtest(strategy=FixedTwoTickerStrategy(), start=date(2024, 1, 2), end=date(2024, 12, 31), conn=conn, cost_bps=0)
    counts = {d: n for d, _, _, n in result.nav_series}
    assert counts[date(2024, 6, 28)] == 2
    assert counts[date(2024, 7, 12)] == 1 and counts[date(2024, 9, 9)] == 1
```
(fixture는 2024-01-02부터 252일 연속 달력일로 가격을 넣어 마지막 날이 2024-09-09다. 테스트 DB의 `DELETE`는 임시 파일이라 유일본 규칙과 무관하다.)

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/unit/web/test_exporter_targets.py tests/unit/backtest/test_engine.py -q` → KeyError / `counts[...] == 2`.

- [ ] **Step 3: 구현 → 통과 확인** — `uv run pytest tests/unit -q` PASS.

- [ ] **Step 4: 실데이터 반영·브라우저 확인**

Run: `uv run thirteen-f backtest --all --start 2024-01-02; uv run thirteen-f export`
Expected: `#/plan`에서 GTLS·LBRDA·LBRDK·LEG·FLYX-WS처럼 가격이 끊긴 종목에 `STALE` 배지와 주의 문구. README Backtest Snapshot 표의 수치가 바뀌었으면 갱신(소폭).

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/web/exporter.py src/thirteen_f/backtest/engine.py tests/unit/web/test_exporter_targets.py tests/unit/backtest/test_engine.py src/thirteen_f/web/static/hf-plan.jsx _claude_docs/TROUBLESHOOTING.md _claude_docs/DATA_FORMATS.md _claude_docs/FRONTEND_PARITY.md README.md
git commit -m "feat(backtest,web): treat tickers without recent prices as untradeable"
```

### Phase 3 DoD

- `uv run pytest tests/unit -q` PASS, ruff 통과, CI 녹색.
- `targets.json`의 `next_rebalance`가 2025Q4 사례에서 `2026-02-17`; `check-filings` 실환경 동작·스케줄러 등록(승인 시); Plan 탭에 STALE 배지.
- 사용자가 `/brain`으로 [[13f-tracker-overview]]를 갱신한다 (서버 자동 시작·감지기·기한 규칙).

---

## 부록 A — 실행 메모 (구현 에이전트용)

- **환경이 막혔을 때**: `uv run` 실패가 `os error 4551`이면 Smart App Control이다. `scripts\py.ps1`(Task 0.4)로 바꿔 실행하고, 코드 버그로 오진하지 않는다. 차단은 간헐적이라(10-27 해제, 10-31 재차단) 세션마다 다를 수 있다.
- **DB 파일 잠금**: `serve`가 떠 있어도 export·analyze는 된다(서버는 요청마다 read-only로 연다). 반대로 collect·analyze·backtest가 돌 때 `targets`·export를 함께 돌리면 `IO Error: Cannot open file`. 한쪽이 끝난 뒤.
- **Quarto·Tailscale**은 이 PC에 없다. `update`에는 `--skip-report`를 붙이고, `report` 관련 변경은 CLI 검사 테스트까지만 검증한다.
- **문서 갱신 규칙**: 각 Task의 Files에 적힌 문서를 같은 커밋에 넣는다. TROUBLESHOOTING은 "해결된 항목은 지운다"가 규칙이다. `_brain`은 쓰지 않는다.
- **테스트 건수**: Phase 0 기준 204. Task마다 늘어나므로 CLAUDE.md·README의 숫자는 Task 2.7(또는 마지막 Task)에서 한 번에 실제 값으로 맞춘다.
- **스윕은 사본에서**: `scripts/sweep_backtests.py`는 `data/sweep/13f.sweep.duckdb`에 run을 쌓는다. 본 DB에 run이 누적되는 것은 `backtest --all`뿐이며 SPA는 전략별 최신 run만 쓴다.

## 부록 B — Task ↔ 점검 항목 대응

| 점검 항목 (spec) | Task |
|---|---|
| §1 작업 트리 82개 누락 · Drive 미러 · venv · SAC · export 없음 | 0.1 · 0.2 · 0.3 · 0.4 · 0.6 |
| §1 integration `test_serve`가 uv에 의존 | 0.5 |
| §2.1 exit 시그널 0건 | 1.3 |
| §2.2 ETF·복수 클래스 | 1.6 |
| §2.3 컨센서스 분모 14 vs 13 | 1.4 |
| §2.4 천 달러 단위 | 1.5 |
| §2.5 가격 끊긴 보유 종목 · 공휴일 기한 | 3.3 · 3.1 |
| §3 `update` 2011Q1 · 백업 없음 · 가격 전체 재다운로드 | 1.1 · 1.2 · 1.7 (+2.9) |
| §3 CI 없음 · ruff 107 | 2.2 · 2.1 |
| §3 가짜 스파크라인 · SIM 엔진 | 2.4 · 2.3 |
| §3 legacy dashboard · 의존성 · analysis.toml · supplement.py · 문서 수치 · React dev 빌드 | 2.5 · 2.6 · 2.7 |
| §3 continuity 39초 | 2.8 |
| §5 Q3 반영 루틴 · 재스윕 | 1.8 |
| `_brain` 미결: 서버 자동 시작 · 새 공시 감지 | 0.6 · 3.2 |

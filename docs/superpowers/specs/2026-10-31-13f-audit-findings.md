# 13F Tracker 점검 결과 (2026-10-31)

> 이 문서는 `docs/superpowers/plans/2026-10-31-13f-audit-remediation.md`가 근거로 삼는 점검 기록이다.
> 수치는 2026-10-31 집 PC에서 HEAD `e47226a`(= `origin/main`)와 `data/13f.duckdb`(2026-09-15 수집, 2024Q1~2026Q2)를 대상으로 실측했다.
> 저장소는 수정하지 않았다. 테스트·정적 검사는 HEAD를 임시 폴더에 내보내 실행했다.
> §1의 82개 누락·Google Drive 판단은 같은 날 DriveFS 로그(`%LOCALAPPDATA%\Google\DriveFS\Logs`)와 폴더 시각을 대조해 정정했다 — 누락은 Drive와 무관하다.

## 0. 요약

- 코드 건강: unit **204 passed**(Python 3.12.15·3.14.8 모두), ruff **107건**, mypy **38건**(문서 기준선과 같은 수준). lookahead 가드·정정본 규칙·CUSIP 매핑(최신 분기 미매핑 10건, 금액 0.12%)·NaN 가격 0건·서버 기본값 정상.
- 문제 세 갈래: ① 이 PC의 작업 폴더가 실행 불가 상태(환경), ② `signals_quarterly`에 `exit` 행이 0건(버그), ③ 알고리즘 정의 미결(ETF·복수 클래스)이 실제 매매 목록(Plan 탭)에 들어와 있음.

## 1. 환경 (이 PC, 코드 문제 아님)

| 증상 | 증거 | 조치 |
|---|---|---|
| 추적 파일 158개 중 **82개가 디스크에 없음** — `_claude_docs/*`, `tests/**`, `src/thirteen_f/web/static/*`, `src/thirteen_f/web/__init__.py`, `src/thirteen_f/_legacy_dashboard/**`, `참고/*` | HEAD = origin/main, 수정 파일 0, stash 0, 휴지통에 없음. 디스크 파일은 2026-10-09 11:51~11:53 복원 복사로 생성(mtime 보존)됐고, 비어 있는 폴더(`web/static`·`web/data`·`_legacy_dashboard`·`tests/unit/{backtest,collect,web}`)의 mtime은 2026-10-09 00:52 그대로다 → Drive 첫 실행(2026-10-12 22:11) **전부터** 없었다. 복원 출처는 미확인 | `git restore .` |
| 프로젝트 폴더 자체가 Drive '내 컴퓨터'의 **양방향 미러** 동기화 폴더 | DriveFS 로그 `sync_type=MIRROR medium=FOLDER title="13. 13f-tracker"`, 2026-10-12 22:15 등록 (같은 방식: `0. Research`·`cae-copilot`). 2026-10-13 06:26·14:25 KST(각각 Drive 재시작 직후)에 757건을 폴더 안으로 내려받음 — 손상 없음(`git fsck` 정상). 동기화량 `.venv` 23,506파일·749MB, `data/` 302MB(DuckDB 105MB), `.git` 1,164파일 — 추적 소스는 158개. git이 `.git`을 건드리면 루트에 `.tmp.driveupload` 생성(2026-10-31 01:47) | 위험: 양방향이라 재연결·충돌 때 클라우드 사본이 `.git`·작업 트리를 덮어쓸 수 있음, 파일별 업로드라 실행 중 올라간 DB·`.wal` 사본은 시점이 어긋날 수 있음, `.venv`는 PC 전용 경로라 백업 가치 없음. 코드는 GitHub에 전부 있음(미push 0). → 폴더는 옮기지 않고 Drive에서 **동기화 중지**(Drive 안내문: "기존 파일은 컴퓨터에 유지됩니다"), `data/backups/`만 별도 동기화 (plan Task 0.2) |
| `.venv` 깨짐 | `pyvenv.cfg`: `home = C:\Users\zenit\miniconda3`(옛 계정), `version_info = 3.12.9` | `uv sync` (전역 고정 3.14 적용; `uv.lock`은 3.12·3.14 모두 설치됨) |
| **Smart App Control**이 uv venv 런처 차단 (간헐적) | CodeIntegrity 3077, 2026-10-31 01:55~01:57; `uv run` → `uv trampoline failed to spawn Python child process (os error 4551)`; `_brain` [[windows-smart-app-control-python-block]]은 10-27에 저절로 풀린 기록 | uv 관리 인터프리터(`%APPDATA%\uv\python\cpython-3.14.8-windows-x86_64-none\python.exe`) 직접 실행 + `PYTHONPATH=.venv\Lib\site-packages;src` 로 우회 (이번 점검도 이 방식) |
| `src/thirteen_f/web/data/` 비어 있음 | export 산출물 없음 → SPA 빈 화면 | `thirteen-f export` |
| Quarto·Tailscale 미설치 (재설치 PC) | `Get-Command quarto/tailscale` 없음 | `report`는 `--skip-report`, 원격 접속은 재설치 후 |

## 2. 정확성

### 2.1 `exit` 시그널 부재 (버그, `analyze/diff.py`)

`compute_signals_quarterly`의 SQL은 **현재 필링에 있는 종목 행만** 만들고 `LAG`로 직전 행과 비교한다. 전량 매도된 종목은 행 자체가 없어 `exit`가 생길 수 없다. Spec §6.1·consensus의 `change_type != 'exit'` 필터·`continuity_from_changes`의 reset 규칙이 모두 exit 행을 전제하므로 결함이다.

| 실측 | 값 |
|---|---|
| `change_type` 분포 | decrease 4,383 · increase 3,773 · new 2,766 · hold 2,038 · **exit 0** |
| 다음 분기도 제출했는데 종목 행이 사라진 경우 (= 누락된 청산) | **2,136건**, 14명 전원 |
| 공백 뒤 재진입인데 `new`가 아닌 행 | **851건** (최신 분기 178건) |

파급: `new_buy_count` 과소집계(NewBuyOnly 후보·헤드라인 "신규 매수" 오류), continuity가 매도에 리셋되지 않음(예: Dalio OMCL — 2024Q4 후 사라졌다 2026Q2 재진입인데 continuity 0.25), `test_diff.py`는 파이프라인이 쓰지 않는 순수 함수 `classify_change`만 검증. SPA는 dense 배열(`HOLDINGS[mgr][ticker][q]`)로 EXIT를 맞게 표시하므로 "backend가 정답" 원칙과도 어긋난다.

### 2.2 ETF·복수 클래스 (정의 미결 → 매매 목록 오염)

현재 `ConsensusTopK(3,10)` 목표: AMZN, GOOGL, GOOG, AAPL, **SPY**, BRK-B, V, TSM, QSR, META (각 10%). 최신 분기 컨센서스에 SPY 4명, IWM·EWY·RSP 각 2명, GOOG·GOOGL 각 6명. 같은 발행사 쌍: GOOG/GOOGL, BRK-A/B, LBRDA/LBRDK, FOX/FOXA. `cusip_ticker_map.is_etf`는 이미 채워져 있다(OpenFIGI securityType).

### 2.3 컨센서스 분모

`score.compute_total_scores`가 `COUNT(*) FROM managers` = 14를 분모로 쓰지만 2025Q4부터 제출자는 13명(Burry 2025Q3 이후 13F 없음).

### 2.4 천 달러 단위 보고자

Druckenmiller(Duquesne)·Klarman(Baupost)의 `value_usd / (shares × 분기말 종가)` 중앙값이 **0.001**. 총액이 $0.0B로 표시된다. `normalize_value`는 제출일(2023-01-03 경계)로만 판단한다.

### 2.5 소소한 것

- 보유 중 5종목 가격 끊김: GTLS(2026-07-16), LBRDA·LBRDK(08-21), LEG(08-27), FLYX-WS(없음). 인수·합병·워런트라 엔진은 마지막 가격 유지(수익률 0) 처리.
- `_next_rebalance`는 주말만 보정해 2025Q4 기한을 02-16으로 계산하지만 실제 기한은 02-17(Presidents' Day).

## 3. 운영·품질

- `update`가 `collect`를 `--start` 없이 호출 → 기본값 2011Q1부터 수집(문서화된 함정, `_brain` 미결).
- `download_prices`가 매번 전 종목 전체 기간을 다시 받음(~1,800 ticker, 약 2시간).
- `update` 시작 시 자동 백업 없음 (`data/13f.duckdb`는 git 밖 유일본).
- CI 없음(`.github/` 없음). unit 테스트는 네트워크 불필요, 21~36초.
- SPA: `hf-data.js:buildWeeklyPrices`가 분기말 가격 보간 + `Math.sin` 노이즈로 `pxWeekly`를 만들어 "PRICE 12W" 스파크라인과 종목 상세 가격 차트에 **가짜 주가 흐름**을 그린다. `runStrategy` 브라우저 시뮬(SIM 배지)은 `s.yld`(export에 없음 → NaN)와 전 종목 평균 벤치마크를 쓴다. 기본 8전략은 전부 backend run이 있다.
- `_legacy_dashboard/`(1,500줄, Streamlit 미설치라 실행 불가) 중 Quarto가 쓰는 것은 `charts.py`의 4개 함수뿐. mypy 38건 중 20건이 여기서 나온다. `.streamlit/config.toml`도 잔존.
- `pyproject.toml`: `jupyter`·`plotly`는 Quarto 전용인데 런타임 의존성, `polars`는 import하는 곳이 없음.
- `config/analysis.toml`(읽는 코드 없음), `scripts/supplement.py`(2026-05 일회성) 잔존.
- 문서의 "unit 189건"은 실제 204건.
- `continuity.update_continuity_scores`: Python 루프 + `executemany` UPDATE 12,960행, 2026-09-15 로그 기준 약 39초.
- ruff 107건 내역: E501 53, I001 26, F401 10, UP035 6, B905 5, E402 2, F541 2, B904 1, F841 1, UP037 1 — 45건은 `--fix`로 자동 수정.

## 4. 우선순위 (Priority = (Impact + Risk) × (6 − Effort))

| 순위 | 항목 | I | R | E | 점수 | Phase |
|---|---|---|---|---|---|---|
| 1 | 작업 트리 복구·venv 재생성·Drive 동기화 정리·export | 5 | 5 | 1 | 50 | 0 |
| 2 | diff exit·재진입 수정 + SQL 테스트 | 4 | 5 | 3 | 36 | 1 |
| 3 | `update` 2011Q1 footgun 제거 | 3 | 4 | 1 | 35 | 1 |
| 4 | ETF 제외·발행사 단위 합산 | 4 | 4 | 3 | 32 | 1 |
| 5 | GitHub Actions CI | 3 | 3 | 1 | 30 | 2 |
| 6 | `update` 자동 백업 | 2 | 4 | 1 | 30 | 1 |
| 7 | 브라우저 SIM 엔진 제거 | 2 | 3 | 1 | 25 | 2 |
| 8 | 가격 증분 다운로드 | 4 | 2 | 3 | 24 | 1 |
| 9 | 가짜 스파크라인 제거 | 3 | 3 | 2 | 24 | 2 |
| 10 | 컨센서스 분모 / 천 달러 보정 | 2·2 | 3·2 | 1·2 | 20 / 16 | 1 |
| 11 | legacy dashboard 정리 | 1 | 2 | 2 | 12 | 2 |
| 12 | 의존성·문서·React production·continuity 벡터화 | 1 | 1 | 1 | 10 | 2 |
| 13 | 공휴일 기한·새 공시 감지기·상장폐지 종목 처리 | 2 | 2 | 3 | 12 | 3 |

## 5. 일정 제약

- **2026Q3 13F 기한 = 2026-11-16(월)** (9/30 + 45일 = 11/14 토 → 월). 이튿날(11-17)부터 수집해야 매니저 전원분이 들어온다.
- 점수를 바꾸는 변경(2.1·2.2·2.3·2.4)은 Q3 수집 **전에** 끝내고, Q3 반영 후 `scripts/sweep_backtests.py`를 **한 번만** 다시 돌려 고원 유지 여부를 확인한다 ([[backtest-strategy-comparison-fairness]] §4·§7).

## 6. 참고 (`_brain`, 읽기 전용)

[[13f-tracker-overview]] · [[sec-13f-data-pipeline-pitfalls]] · [[backtest-strategy-comparison-fairness]] · [[windows-smart-app-control-python-block]] · [[windows-subprocess-tree-orphan-uv]] · [[no-cache-not-retroactive-asset-versioning]] · [[home-pc-python-default-3-14]]

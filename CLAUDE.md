# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# 13F Portfolio Tracker

미국 투자 거장 14명의 SEC 13F-HR 공시를 EDGAR에서 수집해 시그널·종합 점수·백테스트로 가공하고, 정적 SPA와 Quarto 리포트로 보여주는 개인용 Python 도구. Phase 0~5 완료 — 진행 현황·데이터 규모·백테스트 수치는 `README.md`에 기록한다.

## Read First

작업이 아래에 해당하면 코드를 고치기 전에 해당 문서를 먼저 읽는다.

- 단계별로 읽고 쓰는 테이블, 모듈 책임, web·LLM 계층 구조, 설계 문서 지도 → `_claude_docs/ARCHITECTURE.md`
- DuckDB 테이블 의미, JSON export 형태, `config/` 형식, 환경변수 → `_claude_docs/DATA_FORMATS.md`
- 새 분기 반영, 매니저 CIK 변경·추가·제외, 전략·시그널·스키마·SPA·CLI·LLM 프롬프트 변경 → `_claude_docs/WORKFLOWS.md`
- 테스트 실패·skip, 수집·가격 누락, 백테스트 수치 이상, SPA·`/api/ask`·Gemini 오류, DuckDB·`uv sync` 파일 잠금 → `_claude_docs/TROUBLESHOOTING.md`
- 어떤 값을 backend와 frontend 중 어디서 계산하는지 → `_claude_docs/FRONTEND_PARITY.md`
- 공식·정책의 설계 근거 → `docs/superpowers/specs/2026-05-20-13f-tracker-design.md` (Phase 0~4), `docs/superpowers/plans/2026-05-22-13f-frontend-migration.md` (Phase 5)
- EDGAR 요청 규약, 13F XML 구조 → `참고/edgar_notes.md`
- SPA 디자인 토큰·화면 명세 → `handoff/README.md` §4–5, `handoff/design/` (git 미추적 로컬 자료)

## Commands

모든 명령은 저장소 루트에서 실행한다 — CLI가 `config/`, `data/`, `src/thirteen_f/web/data/`, `reports/quarto/`를 cwd 기준 상대경로로 쓰고 `.env`도 cwd에서 읽는다.

```bash
uv sync
cp .env.example .env                        # SEC_USER_AGENT 필수 (비면 load_settings()가 ValueError)
uv run python scripts/init_db.py            # 12 테이블 생성 + 기존 DB 마이그레이션, 재실행 안전

uv run thirteen-f collect --start 2024Q1    # 기본값 2011Q1 — 기존 DB와 같은 시작 분기를 명시
uv run thirteen-f analyze                   # signals·consensus·total_scores를 지우고 전체 재계산
uv run thirteen-f backtest --all --start 2024-01-02   # 기본 8개(Buffett·Druckenmiller 복제 포함), 실행마다 run 누적
uv run thirteen-f backtest --strategy ScoreTopK --start 2024-01-02
uv run python scripts/sweep_backtests.py    # 파라미터 탐색 — DB 사본(data/sweep/)에서 실행, 결과 CSV
uv run thirteen-f export                    # DuckDB → src/thirteen_f/web/data/*.json
uv run thirteen-f serve                     # http://127.0.0.1:8765, 장시간 실행이라 update에 없음
uv run thirteen-f report --latest --open    # Quarto CLI 필요 → reports/output/_latest/
uv run thirteen-f update                    # collect(--start 없이) → analyze → backtest --all → export → report, --skip-* 로 제외

uv run pytest tests/unit                    # 회귀 기준: 189건, 약 30초, 네트워크 불필요
uv run pytest tests/unit/web/test_server.py::test_root_serves_static_index_html   # 단일 테스트
uv run pytest tests/unit -k consensus       # 키워드 필터
uv run pytest tests/integration             # 4건 (= -m integration), collect e2e는 VCR 카세트가 없으면 skip

uv run ruff check <수정한 파일>              # 기준선에 기존 위반이 있어 파일 단위로 확인
uv run mypy src/thirteen_f
```

## Architecture

DuckDB 파일 하나(`data/13f.duckdb`, git 밖)가 단계 사이의 유일한 연결점이다. 단계끼리는 함수를 호출하지 않고 앞 단계가 남긴 테이블만 읽으므로, 필요한 테이블만 있으면 어느 단계든 단독으로 다시 실행할 수 있다.

```
managers.yaml·EDGAR·OpenFIGI·yfinance ─ collect ─▶ managers, filings, holdings, cusip_ticker_map, prices
                                         analyze ─▶ signals_quarterly, consensus_quarterly, total_scores
                                        backtest ─▶ backtest_runs, _curves, _metrics, _holdings
DuckDB ─ export ─▶ web/data/*.json ─ serve(FastAPI) ─▶ SPA(web/static), /api/ask ─▶ Gemini
       └ report ─▶ Quarto(reports/quarto) ─▶ reports/output/<분기>/
```

- 단계 진입점은 `collect/`·`analyze/`의 `pipeline.py`, `backtest/runner.py`+`engine.py`, `web/cli.py`. `cli.py`는 옵션을 받아 위임만 하며 import는 함수 안에 둔다.
- SPA는 빌드 단계가 없다. `web/static/index.html`이 CDN의 React 18 UMD와 Babel standalone으로 `.jsx`를 브라우저에서 변환하고, 파일끼리는 `<script>` 로드 순서와 `Object.assign(window, {...})` 전역으로 연결된다.
- 사실 데이터는 backend exporter가 정답이고 frontend는 표시용 파생 계산만 한다. 두 계산이 어긋나면 frontend를 backend에 맞춘다.
- Gemini는 선택 기능이다. `GOOGLE_API_KEY`가 없으면 Quarto LLM 셀은 안내 문구, `/api/ask`는 503을 내고 나머지 기능은 그대로 동작해야 한다.
- `_legacy_dashboard/`는 Phase 4 Streamlit 격리본이다. Quarto `01_overview.qmd`·`04_backtest.qmd`가 `_legacy_dashboard.charts`를 import하므로 유지하되 새 기능은 넣지 않는다.

## Invariants

어기면 에러 없이 결과만 틀어지므로, 관련 코드를 고칠 때마다 확인한다.

- **Lookahead 차단** (Spec §7.4): 전략 SQL은 `filings.filed_at <= as_of_date`로 거른다. 13F는 분기말 후 최대 45일 뒤 공개되므로 `period_of_report` 기준으로 진입하면 미래 정보를 쓰게 된다. 분기 집계 테이블(`total_scores`·`consensus_quarterly`)은 매니저 전원의 보유를 합친 값이라 그 분기 13F-HR 원본이 **모두** 제출된 뒤에만 쓴다 (`backtest/strategy.py:latest_public_period`) — 첫 제출자 기준으로 쓰면 최대 11일 앞선다. 전략별 검증은 `tests/unit/backtest/test_lookahead_guard.py`·`test_score_top_k.py` (MultiManager는 `test_multi_manager.py`).
- **정정본** (Spec §5.2): 같은 (cik, period_of_report)에서 최신 `filed_at` 1건만 `superseded_by IS NULL`이다 (`collect/loader.py:mark_supersedes`). `holdings`를 직접 읽는 SQL은 이 조건을 붙인다 — 빠뜨리면 원본과 정정본이 이중 집계된다. 추가 공개분만 담은 NEW HOLDINGS 정정은 원본을 가리지 않도록 적재하지 않는다 (`collect/pipeline.py`).
- **value 단위** (Spec §5.3): `holdings.value_usd`는 항상 달러. `filed_at < 2023-01-03` 필링은 천 달러로 보고돼 ×1000 한다 (`collect/parser.py:normalize_value`).
- **holdings PK** `(accession_no, cusip, title_of_class, put_call)`: 뒤 두 컬럼은 `NOT NULL DEFAULT ''` — NULL이 들어가면 PK 중복 검사가 동작하지 않는다. 같은 PK로 분할 보고된 행은 적재 전에 합산한다 (`upsert_holdings`).
- **점수 가중치** (Spec §6.1): `config/scoring.toml [weights]` 합이 1.0(±0.01)이 아니면 `load_weights`가 예외를 낸다. 기본값 consensus 0.30, conviction 0.30, continuity 0.20, cloning_quality 0.20.
- **CUSIP → ticker** (Spec §5.1 1e): 첫 글자가 알파벳인 CINS 코드(외국 소재 미국 상장사, 예: Chubb)는 `ID_CUSIP`이 아니라 `ID_CINS`로 조회해야 찾는다. OpenFIGI 결과 중 US primary 거래소 코드(`cusip_mapper.US_PRIMARY_EXCH_CODES`)만 채택하고 `/`·`.`은 `-`로 바꾼다 (yfinance 표기). 매핑 실패는 `ticker = NULL`로 두고 전략에서 제외한다.
- **스키마 SSOT**: `scripts/init_db.py`. Spec §4.2의 DDL은 이와 같게 유지한다 (변경 절차는 `_claude_docs/WORKFLOWS.md`).

## Workflow Rules

- **Phase 단위 진행**: 한 Phase(또는 plan Chunk)를 마치면 멈추고 DoD(Spec §10, plan의 DoD 검증 Task) 충족 여부를 보고한 뒤 사용자 승인을 받고 다음으로 넘어간다.
- **TDD**: 실패하는 테스트 → 최소 구현 → `uv run pytest tests/unit` 전체 통과 → 커밋 (plan의 step 단위).
- **stage는 파일을 지정해서** (`git add <path>`): 루트에 커밋 대상이 아닌 미추적 파일(`handoff/`, `data/logs/`, `reports/output/`, `.omc/` 등)이 있어 `git add .`나 `-A`는 이것들을 함께 끌어들인다.
- **정적 검사**: 수정한 파일의 ruff·mypy 위반 수가 수정 전보다 늘지 않게 한다. 기존 위반 일괄 정리는 요청받았을 때만 한다 — 무관한 diff가 섞인다.
- **`data/13f.duckdb`는 git 밖의 유일본**이다 (재수집에 수십 분 이상 + API 한도). 파일 삭제, 테이블 DROP·DELETE, 재생성 전에는 사용자에게 확인하고 복사본을 만든다. `scripts/init_db.py` 재실행은 idempotent라 여기에 해당하지 않는다.
- **frontend는 `src/thirteen_f/web/static/`에서만 수정**한다. `handoff/design/`은 구현 전 디자인 원본이며, `handoff/`의 구조 권고(Next.js, "hf-data.js가 알고리즘 정답")는 실제 구현과 다르다.

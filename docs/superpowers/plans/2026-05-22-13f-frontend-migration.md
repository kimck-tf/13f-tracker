# 13F Terminal — Streamlit → Static SPA Migration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `handoff/design/`의 9페이지 정적 HTML/JSX 프로토타입을 production frontend로 만들고, Python 백엔드는 DuckDB → JSON exporter + 정적 서버 + /api/ask LLM 엔드포인트만 담당하도록 재구성. Streamlit dashboard는 폐기.

**Architecture:** FastAPI 정적 서버가 `static/`(handoff/design 복사) + `data/*.json`(DuckDB dump) + `/api/ask`(Gemini chat)를 호스팅. 프론트엔드는 hash router 기반 React 18 SPA가 mock 객체 대신 fetch JSON으로 동작. 백테스트 holdings log를 위해 신규 `backtest_holdings` 테이블 추가.

**Tech Stack:** Python 3.11+ (uv) / FastAPI + uvicorn / DuckDB / Pydantic v2 / React 18 + Babel-standalone (CDN) / Pretendard + JetBrains Mono / Plotly 폐기

---

## Context

현재 13F-tracker는 Streamlit 기반 5페이지 대시보드(다크 톤, IBM Plex, 그린 accent)로 동작 중. 사용자가 Claude Code Design을 통해 새로 디자인한 9페이지 정적 HTML/JSX 프로토타입을 `handoff/design/`에 저장. 새 디자인은 **라이트 톤 + Pretendard + 블루 accent(#1d6dc8) + Koyfin 스타일 정보 밀도**의 다른 톤이며, 기존과 페이지 구성·인터랙션도 전면 다름.

이번 작업의 목표는 **Streamlit을 폐기하고**, `handoff/design`의 정적 프로토타입을 production frontend로 만들고, Python 백엔드는 **DuckDB → JSON exporter + 정적 서버 + /api/ask LLM 엔드포인트**만 담당하도록 재구성하는 것.

## Goals

1. `handoff/design/`의 9페이지 SPA를 실 DuckDB 데이터로 동작시킨다 (mock 객체 → fetch JSON).
2. Python은 ① DuckDB → JSON exporter ② 정적 파일 + JSON 서빙 ③ /api/ask Gemini chat 엔드포인트만 제공.
3. 기존 Streamlit dashboard 모듈은 `_legacy_dashboard/`로 격리 후 Chunk E에서 제거.
4. 사용자 명령은 `thirteen-f export && thirteen-f serve` 두 단계.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│ Browser (Static SPA — Pretendard light, blue accent)    │
│  - hf-app.jsx hash router                               │
│  - 9 pages: Home/Managers/Compare/Stocks/Changes/...    │
│  - hf-data.js: bootstrapFromJson() fetches /data/*.json │
└──────────────┬──────────────────────────────────────────┘
               │ HTTP
┌──────────────▼──────────────────────────────────────────┐
│ FastAPI (web/server.py · `thirteen-f serve`)            │
│  - GET /        → static/13F Terminal.html              │
│  - GET /data/*  → JSON dump (exporter 결과)             │
│  - GET /api/health  → {llm_available: bool}             │
│  - POST /api/ask    → Gemini chat (structured cards)    │
└──────────────┬──────────────────────────────────────────┘
               │ read-only
┌──────────────▼──────────────────────────────────────────┐
│ DuckDB data/13f.duckdb (변경 없음)                       │
│  - 11 tables + 신규 backtest_holdings 테이블 추가       │
└─────────────────────────────────────────────────────────┘
```

## User Decisions (확정)

1. **디자인 톤**: 라이트 + Pretendard + 블루 accent로 완전 전환 (다크 폐기)
2. **페이지 범위**: 9 페이지 완전 구현 (Home/Managers/Compare/Stocks/Changes/Consensus/Backtest/Builder/Ask)
3. **구현 전략**: 정적 HTML 프로토타입 활용, Streamlit 폐기
4. **Ask LLM**: Gemini chat 실연결 (`/api/ask` 엔드포인트)
5. **MultiManager 전략**: Python에 신규 구현 추가 (7번째 전략)
6. **Tweaks panel**: density(compact/regular/cozy) 토글만 유지, host protocol 제거
7. **가격 시계열**: daily 그대로 export, ticker별 파일 분할

## File Structure

```
src/thirteen_f/
  web/                        # NEW
    __init__.py
    schemas.py                # Pydantic models — frontend/backend JSON contract SSOT
    queries.py                # SQL helpers (dashboard/tables.py에서 이주)
    exporter.py               # DuckDB → JSON dumper
    server.py                 # FastAPI app
    ask_context.py            # 사용자 질문에서 ticker/manager 키워드 추출 → small fetch
    cli.py                    # 'thirteen-f export', 'thirteen-f serve'
    static/                   # handoff/design 복사 (한 번)
    data/                     # JSON dump 출력 (gitignore)
      prices/                 # 16 ticker별 separate file
  backtest/
    strategies/
      multi_manager.py        # NEW — 7번째 전략
    engine.py                 # MODIFY — holdings log hook 추가
  llm/
    prompts.py                # ADD — chat_prompt(question, context)
    summary.py                # ADD — chat_reply()
  cli.py                      # MODIFY — serve/export 추가, dashboard deprecation
  _legacy_dashboard/          # Chunk E에서 dashboard/를 여기로 이동, 최종 삭제

scripts/init_db.py            # MODIFY — backtest_holdings 테이블 신설
config/managers.yaml          # MODIFY — color 컬럼 추가 (15명)
```

## Data Interface (JSON Schemas)

`web/data/` 아래 다음 파일을 생성:

| 파일 | 형상 | 출처 |
|---|---|---|
| `meta.json` | `{generated_at, latest_period, data_version, mgr_count, stock_count, llm_available}` | derive |
| `quarters.json` | `[{key:"2024Q2", label:"Q2'24", date:"2024-06-30"}]` | filings.period_of_report 정렬 + Q-label 생성 |
| `quarters_index.json` | `{"2024-06-30": 0, ...}` | quarters.json 역인덱스 |
| `managers.json` | `[{id, name, firm, style, color, avatar, note}]` | managers + style→color 매핑 + avatar 자동(label 첫 2글자) |
| `stocks.json` | `[{t, n, s, i?, mc?, px:[Nq close], yld?}]` (가격은 분기말만) | cusip_ticker_map JOIN prices 분기말 |
| `prices/{TICKER}.json` | `{date:[], close:[]}` daily | prices 테이블 직접 |
| `holdings.json` | `{mgrId: {ticker: [Nq shares]}}` | holdings JOIN cusip_ticker_map, ticker 키로 통일 |
| `holdings_unmapped.json` | `{mgrId: [{cusip, name_of_issuer, [shares]}]}` | mapping 실패 cusip 분리 보존 |
| `backtest.json` | `[{run_id, type, params, name, color, equity[], dd[], qrets[], holdingsLog[], metrics:{...}}]` | backtest_runs + curves + metrics + 신규 backtest_holdings |
| `llm_summary.json` | `{[period]: {headline, top_signals}}` | summary.headline_summary + explain_top_signals 캐시 |

**중요**:
- `signals.json` / `consensus.json` 별도 export 안 함 — frontend가 `holdings.json`에서 `classifyAction(prev, curr)`로 derive (디자인의 helper와 동일).
- ticker가 frontend의 1차 키 — cusip 미해석 종목은 `holdings_unmapped.json`으로 격리해 무시.
- `equity`는 quarterly resample (frontend의 8-quarter index와 일치).
- `holdingsLog`는 신규 `backtest_holdings` 테이블에서 (engine.py 수정으로 분기말 snapshot 저장).

## DB Schema 신규 — `backtest_holdings`

```sql
CREATE TABLE IF NOT EXISTS backtest_holdings (
  run_id      VARCHAR NOT NULL REFERENCES backtest_runs(run_id),
  rebalance_date DATE NOT NULL,
  ticker      VARCHAR NOT NULL,
  weight      DOUBLE NOT NULL,
  PRIMARY KEY (run_id, rebalance_date, ticker)
);
```

engine.py의 백테스트 루프에서 분기 경계마다 현재 target_positions를 이 테이블에 INSERT. 기존 단위 테스트(`tests/unit/backtest/test_engine.py`) 영향 — fixture에 backtest_holdings 동행 검증 추가.

---

## Chunks & Tasks (총 20개)

### Chunk A — 백엔드 기반 (5 tasks)

#### Task A1: web/ scaffold + Pydantic schemas + queries 이주

**Files:**
- Create: `src/thirteen_f/web/__init__.py`
- Create: `src/thirteen_f/web/schemas.py`
- Create: `src/thirteen_f/web/queries.py`
- Modify: `src/thirteen_f/dashboard/tables.py` (re-export shim)
- Test: `tests/unit/web/test_queries.py`

- [ ] **Step 1: web/ 모듈 scaffold**

```python
# src/thirteen_f/web/__init__.py
from .queries import (
    latest_period, manager_list, top_scores, manager_history,
    backtest_curves_df, backtest_metrics_df, get_read_only_conn,
)
__all__ = [...]
```

- [ ] **Step 2: schemas.py — Pydantic JSON contract SSOT**

```python
# src/thirteen_f/web/schemas.py
from datetime import datetime
from pydantic import BaseModel, Field

class QuarterEntry(BaseModel):
    key: str        # "2024Q2"
    label: str      # "Q2'24"
    date: str       # "2024-06-30"

class Manager(BaseModel):
    id: str
    name: str
    firm: str
    style: str
    color: str      # "#1d6dc8"
    avatar: str     # "WB"
    note: str = ""

class Stock(BaseModel):
    t: str          # ticker
    n: str          # name
    s: str          # sector
    i: str | None = None
    mc: float | None = None
    px: list[float] # 분기말 close
    yld: float | None = None

class Meta(BaseModel):
    generated_at: datetime
    latest_period: str
    data_version: str
    mgr_count: int
    stock_count: int
    llm_available: bool
```

- [ ] **Step 3: queries.py — dashboard/tables.py에서 SQL helper 이주**

`latest_period`, `manager_list`, `top_scores`, `manager_history`, `backtest_curves_df`, `backtest_metrics_df`, `get_read_only_conn` 함수를 그대로 이주. dashboard/tables.py는 backward-compatible shim으로 변경:

```python
# dashboard/tables.py (shim)
from thirteen_f.web.queries import *  # legacy import 유지
```

- [ ] **Step 4: 단위 테스트**

```python
# tests/unit/web/test_queries.py
def test_latest_period_returns_iso_date(memory_db):
    # fixture에 1 filing + 1 holding
    p = latest_period(memory_db)
    assert isinstance(p, str)
    assert len(p) == 10  # "YYYY-MM-DD"
```

Run: `uv run pytest tests/unit/web/test_queries.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/web/__init__.py src/thirteen_f/web/schemas.py src/thirteen_f/web/queries.py src/thirteen_f/dashboard/tables.py tests/unit/web/test_queries.py
git commit -m "feat(web): scaffold web/ module with pydantic schemas and queries migration"
```

---

#### Task A2: exporter managers / quarters / meta

**Files:**
- Create: `src/thirteen_f/web/exporter.py`
- Modify: `config/managers.yaml` (color 컬럼 추가)
- Test: `tests/unit/web/test_exporter.py`

- [ ] **Step 1: managers.yaml에 color 컬럼 추가**

```yaml
# config/managers.yaml — 각 manager에 color 추가
- name: Warren Buffett
  label: buffett
  fund: Berkshire Hathaway
  style: value
  color: "#1d6dc8"  # blue
  cik: "0001067983"
  ...
```

스타일별 팔레트:
- value → `#1d6dc8` (blue)
- activist → `#0e8a3b` (green)
- macro → `#b45309` (amber)
- contrarian → `#c8261e` (red)

- [ ] **Step 2: exporter.py — export_managers / export_quarters / export_meta**

```python
# src/thirteen_f/web/exporter.py
import json
from pathlib import Path
from datetime import datetime, UTC
import duckdb
from .schemas import Manager, QuarterEntry, Meta

def export_managers(conn, out_dir: Path) -> None:
    rows = conn.execute("""
        SELECT label, name, fund, style, color, notes
        FROM managers ORDER BY label
    """).fetchall()
    payload = []
    for label, name, fund, style, color, notes in rows:
        avatar = "".join([w[0] for w in name.split() if w])[:2].upper()
        payload.append(Manager(
            id=label, name=name, firm=fund, style=style,
            color=color or "#1d6dc8", avatar=avatar, note=notes or "",
        ).model_dump())
    (out_dir / "managers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def export_quarters(conn, out_dir: Path) -> None:
    rows = conn.execute("""
        SELECT DISTINCT period_of_report
        FROM filings ORDER BY period_of_report
    """).fetchall()
    payload = []
    idx_map = {}
    for i, (period,) in enumerate(rows):
        q = (period.month - 1) // 3 + 1
        year_short = str(period.year)[-2:]
        key = f"{period.year}Q{q}"
        label = f"Q{q}'{year_short}"
        payload.append(QuarterEntry(
            key=key, label=label, date=period.isoformat(),
        ).model_dump())
        idx_map[period.isoformat()] = i
    (out_dir / "quarters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "quarters_index.json").write_text(
        json.dumps(idx_map, ensure_ascii=False, indent=2), encoding="utf-8")

def export_meta(conn, out_dir: Path, llm_available: bool) -> None:
    mgr_count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
    stock_count = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM cusip_ticker_map WHERE ticker IS NOT NULL"
    ).fetchone()[0]
    latest = conn.execute(
        "SELECT MAX(period_of_report) FROM filings"
    ).fetchone()[0]
    meta = Meta(
        generated_at=datetime.now(UTC),
        latest_period=latest.isoformat() if latest else "",
        data_version=str(int(datetime.now(UTC).timestamp())),
        mgr_count=mgr_count,
        stock_count=stock_count,
        llm_available=llm_available,
    )
    (out_dir / "meta.json").write_text(
        meta.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 3: 단위 테스트**

```python
# tests/unit/web/test_exporter.py
def test_export_managers_schema(memory_db, tmp_path):
    export_managers(memory_db, tmp_path)
    data = json.loads((tmp_path / "managers.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    for m in data:
        Manager.model_validate(m)  # schema 검증
        assert len(m["avatar"]) <= 2
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/exporter.py config/managers.yaml tests/unit/web/test_exporter.py
git commit -m "feat(web): export managers/quarters/meta JSON with avatar/color auto-derive"
```

---

#### Task A3: exporter stocks / prices / holdings

**Files:**
- Modify: `scripts/init_db.py` (cusip_ticker_map에 sector/industry 컬럼 추가)
- Create: `scripts/supplement_sector.py` (yfinance로 sector/industry 1회 backfill)
- Modify: `src/thirteen_f/web/exporter.py`
- Test: `tests/unit/web/test_exporter.py` (확장)

**배경 (보강):** 디자인의 `STOCKS[].s` (sector) 필드가 treemap 색·필터에 사용됨. 모두 `"Other"`이면 9 페이지 결과물 품질이 mock보다 크게 떨어짐. 따라서 `cusip_ticker_map`에 `sector`/`industry` 컬럼을 추가하고 yfinance로 1회 backfill한 뒤 export 시 JOIN.

- [ ] **Step 0: cusip_ticker_map에 sector/industry 컬럼 추가**

```python
# scripts/init_db.py — cusip_ticker_map 정의 변경
CREATE TABLE IF NOT EXISTS cusip_ticker_map (
    cusip      VARCHAR PRIMARY KEY,
    ticker     VARCHAR,
    figi       VARCHAR,
    name       VARCHAR,
    sector     VARCHAR,           -- NEW
    industry   VARCHAR,           -- NEW
    is_etf     BOOLEAN,
    updated_at TIMESTAMP DEFAULT now()
);
```

기존 DB는 `init_db()` 안에서 `ALTER TABLE cusip_ticker_map ADD COLUMN IF NOT EXISTS sector VARCHAR;` / `... industry VARCHAR;`를 SCHEMA_SQL 실행 직후 명시적으로 호출하여 idempotent하게 in-place 마이그레이션.

- [ ] **Step 0b: supplement_sector.py — yfinance로 sector 1회 채움**

```python
# scripts/supplement_sector.py
import yfinance as yf
import duckdb
from thirteen_f.core.config import load_settings

def main():
    settings = load_settings()
    conn = duckdb.connect(str(settings.duckdb_path))
    rows = conn.execute("""
        SELECT DISTINCT ticker FROM cusip_ticker_map
        WHERE ticker IS NOT NULL AND (sector IS NULL OR sector = '')
    """).fetchall()
    for (ticker,) in rows:
        try:
            info = yf.Ticker(ticker).info or {}
            sector = info.get("sector") or "Other"
            industry = info.get("industry") or ""
            name = info.get("longName") or info.get("shortName") or ""
            conn.execute("""
                UPDATE cusip_ticker_map
                SET sector = ?, industry = ?,
                    name = COALESCE(NULLIF(name, ''), ?)
                WHERE ticker = ?
            """, [sector, industry, name, ticker])
            print(f"OK {ticker}: {sector} / {industry}")
        except Exception as e:
            print(f"ERR {ticker}: {e}")

if __name__ == "__main__":
    main()
```

운영 가이드: 신규 ticker 추가 시 `uv run python scripts/supplement_sector.py` 재실행. 결과는 DB에 영속이라 export는 빠르게 JOIN만 수행. `mc`(market cap)·`yld`(dividend yield)는 분기마다 흔들리므로 v1에선 제외 — frontend는 해당 필드가 `null`이면 fallback 표시.

- [ ] **Step 1: export_stocks — cusip_ticker_map(name/sector) JOIN prices 분기말 close**

```python
def export_stocks(conn, out_dir: Path) -> None:
    # 분기말 가격 series 구성
    quarters = conn.execute("""
        SELECT DISTINCT period_of_report
        FROM filings ORDER BY period_of_report
    """).fetchall()
    q_dates = [p[0] for p in quarters]

    rows = conn.execute("""
        SELECT ticker,
               COALESCE(NULLIF(name, ''), ticker)       AS display_name,
               COALESCE(NULLIF(sector, ''), 'Other')    AS sector,
               COALESCE(industry, '')                   AS industry
        FROM cusip_ticker_map
        WHERE ticker IS NOT NULL
        ORDER BY ticker
    """).fetchall()

    payload = []
    for ticker, display_name, sector, industry in rows:
        # 분기말 close 가져오기 (가장 가까운 영업일)
        px = []
        for qd in q_dates:
            row = conn.execute("""
                SELECT close FROM prices
                WHERE ticker = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            """, [ticker, qd]).fetchone()
            px.append(float(row[0]) if row else None)
        payload.append({
            "t": ticker,
            "n": display_name,
            "s": sector,
            "i": industry or None,
            "px": px,
        })
    (out_dir / "stocks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 2: export_prices_split — ticker별 daily 파일**

```python
def export_prices_split(conn, out_dir: Path) -> None:
    prices_dir = out_dir / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    tickers = conn.execute("""
        SELECT DISTINCT ticker FROM prices ORDER BY ticker
    """).fetchall()
    for (ticker,) in tickers:
        rows = conn.execute("""
            SELECT date, close FROM prices WHERE ticker = ? ORDER BY date
        """, [ticker]).fetchall()
        payload = {
            "date": [r[0].isoformat() for r in rows],
            "close": [float(r[1]) for r in rows],
        }
        (prices_dir / f"{ticker}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 3: export_holdings + export_holdings_unmapped**

```python
def export_holdings(conn, out_dir: Path) -> None:
    quarters = [p[0] for p in conn.execute("""
        SELECT DISTINCT period_of_report FROM filings ORDER BY period_of_report
    """).fetchall()]
    q_count = len(quarters)
    
    managers = conn.execute("SELECT cik, label FROM managers").fetchall()
    payload = {}
    unmapped = {}
    
    for cik, label in managers:
        by_ticker: dict[str, list[float]] = {}
        unmapped_rows: dict[str, list[float]] = {}
        for i, q in enumerate(quarters):
            rows = conn.execute("""
                SELECT h.cusip, m.ticker, h.name_of_issuer, SUM(h.shares) AS shares
                FROM holdings h
                JOIN filings f ON f.accession_no = h.accession_no
                LEFT JOIN cusip_ticker_map m ON m.cusip = h.cusip
                WHERE f.cik = ? AND f.period_of_report = ?
                  AND f.filed_at <= ? AND f.superseded_by IS NULL
                GROUP BY h.cusip, m.ticker, h.name_of_issuer
            """, [cik, q, q + timedelta(days=180)]).fetchall()
            for cusip, ticker, name, shares in rows:
                key = ticker if ticker else f"__unmapped_{cusip}"
                target = by_ticker if ticker else unmapped_rows
                if key not in target:
                    target[key] = [0.0] * q_count
                target[key][i] = float(shares or 0) / 1e6  # 백만주 단위
        payload[label] = by_ticker
        if unmapped_rows:
            unmapped[label] = unmapped_rows
    
    (out_dir / "holdings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "holdings_unmapped.json").write_text(
        json.dumps(unmapped, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 단위 테스트 확장 + mapping coverage 검증**

```python
def test_holdings_mapping_coverage(memory_db, tmp_path):
    export_holdings(memory_db, tmp_path)
    holdings = json.loads((tmp_path / "holdings.json").read_text(encoding="utf-8"))
    unmapped = json.loads((tmp_path / "holdings_unmapped.json").read_text(encoding="utf-8"))
    total_mapped = sum(len(v) for v in holdings.values())
    total_unmapped = sum(len(v) for v in unmapped.values())
    coverage = total_mapped / (total_mapped + total_unmapped) if (total_mapped + total_unmapped) else 1.0
    assert coverage >= 0.85  # CLAUDE.md known issue 87.3%
```

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/web/exporter.py tests/unit/web/test_exporter.py
git commit -m "feat(web): export stocks/prices(split)/holdings(+unmapped) JSON"
```

---

#### Task A4: backtest_holdings 테이블 + engine hook + backtest exporter

**Files:**
- Modify: `scripts/init_db.py`
- Modify: `src/thirteen_f/backtest/engine.py`
- Modify: `src/thirteen_f/web/exporter.py`
- Test: `tests/unit/backtest/test_engine.py` (확장), `tests/unit/web/test_exporter.py` (확장)

- [ ] **Step 1: scripts/init_db.py — backtest_holdings 테이블 추가 + EXPECTED_TABLES 갱신**

```python
# scripts/init_db.py — SCHEMA_SQL 끝에 추가
CREATE TABLE IF NOT EXISTS backtest_holdings (
    run_id         VARCHAR NOT NULL REFERENCES backtest_runs(run_id),
    rebalance_date DATE    NOT NULL,
    ticker         VARCHAR NOT NULL,
    weight         DOUBLE  NOT NULL,
    PRIMARY KEY (run_id, rebalance_date, ticker)
);
```

`EXPECTED_TABLES` set에 `"backtest_holdings"` 추가. SCHEMA_SQL은 idempotent (`IF NOT EXISTS`)라 기존 DB도 안전.

- [ ] **Step 2: engine.py에 holdings log hook — `_persist_result` 확장**

**배경 (보강):** `engine.py:run_backtest`는 daily loop이고 `quarter_label(d)` helper로 이미 분기 경계 추적 중 (`quarter_navs` 사전이 분기 시작 NAV 저장). 따라서 별도 `_is_quarter_boundary` 함수 불필요. 분기 경계마다 그 시점의 `current_weights` snapshot을 누적한 뒤 `_persist_result`에서 일괄 저장.

```python
# src/thirteen_f/backtest/engine.py — run_backtest 본체 수정 부분
quarter_navs: dict[str, float] = {}
quarter_holdings: dict[str, tuple[date, dict[str, float]]] = {}  # NEW
# {quarter_label: (rebalance_date, {ticker: weight})}

for i, d in enumerate(business_days):
    target = strategy.get_target_positions(as_of_date=d, conn=conn)
    # ... 기존 거래비용·NAV 갱신 로직 그대로 ...
    q_lab = quarter_label(d)
    if q_lab not in quarter_navs:
        quarter_navs[q_lab] = portfolio_value
        # NEW: 분기 첫 영업일의 current_weights snapshot
        if current_weights:
            quarter_holdings[q_lab] = (d, dict(current_weights))

# BacktestResult 객체에 holdings_log 필드 추가
result = BacktestResult(
    ..., holdings_log=quarter_holdings,
)
```

`BacktestResult` dataclass에도 `holdings_log: dict[str, tuple[date, dict[str, float]]] = field(default_factory=dict)` 필드 추가.

`_persist_result`는 holdings_log를 풀어서 INSERT:

```python
def _persist_result(conn, r: BacktestResult) -> None:
    # ... 기존 backtest_runs / backtest_curves / backtest_metrics INSERT 그대로 ...
    rows = []
    for q_lab, (rdate, weights) in r.holdings_log.items():
        for ticker, weight in weights.items():
            rows.append((r.run_id, rdate, ticker, weight))
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO backtest_holdings VALUES (?, ?, ?, ?)",
            rows,
        )
```

run_id는 BacktestResult에 이미 있는 uuid이므로 별도 인자 불필요. `persist=True` 일 때만 저장 (기존 동작 호환).

- [ ] **Step 3: engine 단위 테스트 확장**

```python
def test_engine_persists_quarterly_holdings(memory_db, sample_strategy):
    result = run_backtest(sample_strategy, start, end, memory_db, persist=True)
    rows = memory_db.execute("""
        SELECT DISTINCT rebalance_date FROM backtest_holdings
        WHERE run_id = ? ORDER BY rebalance_date
    """, [result.run_id]).fetchall()
    assert len(rows) >= 1  # 분기 경계 최소 1회
    # weights 합 ≈ 1.0 검증
    s = memory_db.execute("""
        SELECT SUM(weight) FROM backtest_holdings
        WHERE run_id = ? AND rebalance_date = ?
    """, [result.run_id, rows[0][0]]).fetchone()[0]
    assert abs(s - 1.0) < 0.001
```

- [ ] **Step 4: export_backtest — runs/curves/metrics/holdings join (인덱싱·헬퍼 명시)**

**보강 사항:**
- SELECT에 `bench_total_return` 누락 → 추가
- `_resample_quarterly` / `_group_holdings_by_date` 본체 명시
- metrics tuple 인덱싱은 명시적 named unpacking으로 변경 (실수 방지)

```python
from collections import defaultdict
from thirteen_f.core.dates import quarter_label

def _resample_quarterly(curves: list[tuple]) -> tuple[list[float], list[float], list[float], list[float]]:
    """daily curves [(date, nav, bench_nav, pos_cnt)] → 분기말 NAV/벤치/drawdown/quarterly return."""
    by_q: dict[str, tuple] = {}
    for d, nav, bench, _ in curves:
        q_lab = quarter_label(d)
        # 분기말이 더 우선 (덮어쓰기로 마지막 영업일 보존)
        by_q[q_lab] = (d, float(nav), float(bench))
    sorted_q = sorted(by_q.keys())
    equity = [by_q[q][1] for q in sorted_q]
    bench  = [by_q[q][2] for q in sorted_q]
    # drawdown: 누적 최고 대비 하락률
    peak = 0.0
    dd = []
    for v in equity:
        peak = max(peak, v)
        dd.append((v - peak) / peak if peak > 0 else 0.0)
    # quarterly return
    qrets = [0.0]
    for j in range(1, len(equity)):
        prev = equity[j - 1]
        qrets.append((equity[j] / prev - 1.0) if prev > 0 else 0.0)
    return equity, dd, qrets, bench

def _group_holdings_by_date(rows: list[tuple]) -> list[dict]:
    """[(date, ticker, weight)] → [{date, holdings: [{ticker, weight}, ...]}]"""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for d, ticker, weight in rows:
        grouped[d.isoformat()].append({"ticker": ticker, "weight": float(weight)})
    return [{"date": k, "holdings": v} for k, v in sorted(grouped.items())]

def export_backtest(conn, out_dir: Path) -> None:
    runs = conn.execute("""
        SELECT r.run_id, r.strategy_name, r.params_json, r.start_date, r.end_date,
               m.total_return, m.cagr, m.sharpe, m.sortino, m.mdd, m.calmar,
               m.win_rate_quarterly, m.bench_total_return, m.bench_cagr
        FROM backtest_runs r
        LEFT JOIN backtest_metrics m ON m.run_id = r.run_id
        ORDER BY r.created_at DESC
    """).fetchall()

    payload = []
    for (run_id, name, params_json, sd, ed,
         total_ret, m_cagr, m_sharpe, m_sortino, m_mdd, m_calmar,
         m_winq, m_bench_total, m_bench_cagr) in runs:
        curves = conn.execute("""
            SELECT date, nav, benchmark_nav, position_count FROM backtest_curves
            WHERE run_id = ? ORDER BY date
        """, [run_id]).fetchall()
        equity, dd, qrets, bench = _resample_quarterly(curves)

        holdings_log = conn.execute("""
            SELECT rebalance_date, ticker, weight FROM backtest_holdings
            WHERE run_id = ? ORDER BY rebalance_date, weight DESC
        """, [run_id]).fetchall()
        holdings_grouped = _group_holdings_by_date(holdings_log)

        payload.append({
            "run_id": run_id,
            "name": name,
            "params": json.loads(params_json) if params_json else {},
            "equity": equity,
            "dd": dd,
            "qrets": qrets,
            "benchEquity": bench,
            "holdingsLog": holdings_grouped,
            "metrics": {
                "totalRet": total_ret,
                "cagr": m_cagr,
                "sharpe": m_sharpe,
                "sortino": m_sortino,
                "maxDD": m_mdd,
                "calmar": m_calmar,
                "hitRate": m_winq,         # = win_rate_quarterly
                "benchTotalRet": m_bench_total,
                "benchCagr": m_bench_cagr,
            },
        })
    (out_dir / "backtest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 5: Commit**

```bash
git add scripts/init_db.py src/thirteen_f/backtest/engine.py src/thirteen_f/web/exporter.py tests/unit/backtest/test_engine.py tests/unit/web/test_exporter.py
git commit -m "feat(backtest): add backtest_holdings table + engine hook + JSON exporter"
```

---

#### Task A5: `thirteen-f export` CLI + e2e 통합 테스트

**Files:**
- Create: `src/thirteen_f/web/cli.py`
- Modify: `src/thirteen_f/cli.py`
- Test: `tests/integration/test_export_e2e.py`

- [ ] **Step 1: web/cli.py — typer subcommand**

```python
# src/thirteen_f/web/cli.py
import typer
from pathlib import Path
import duckdb
from thirteen_f.core.config import load_settings
from . import exporter

app = typer.Typer(help="Web frontend backend commands")

@app.command()
def export(
    out: Path = typer.Option(
        Path("src/thirteen_f/web/data"),
        help="Output directory for JSON files",
    ),
):
    """DuckDB → JSON dump for static SPA."""
    settings = load_settings()
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "prices").mkdir(exist_ok=True)
    
    typer.echo("Exporting managers / quarters / meta...")
    exporter.export_managers(conn, out)
    exporter.export_quarters(conn, out)
    
    typer.echo("Exporting stocks / prices / holdings...")
    exporter.export_stocks(conn, out)
    exporter.export_prices_split(conn, out)
    exporter.export_holdings(conn, out)
    
    typer.echo("Exporting backtest...")
    exporter.export_backtest(conn, out)
    
    # meta는 마지막
    exporter.export_meta(conn, out, llm_available=bool(settings.google_api_key))
    typer.echo(f"✓ Exported to {out}")
```

- [ ] **Step 2: cli.py 메인에 마운트 + `update` 명령에 export 통합**

```python
# src/thirteen_f/cli.py
from thirteen_f.web.cli import app as web_app
app.add_typer(web_app, name="")  # 또는 직접 명령 등록
```

**보강 사항 — `thirteen-f update` 워크플로우 통합:**
기존 `update`는 collect→analyze→backtest→report 순차 실행. SPA 도입 후 사용자는 `update` 후 매번 `export`를 추가로 실행해야 하는 부담 발생. 이를 해소하기 위해 `update`에 `export` 단계를 추가하고 `--skip-export` 옵션 제공.

```python
# src/thirteen_f/cli.py — update 함수 시그니처 + 본체 확장
@app.command()
def update(
    skip_collect: bool = typer.Option(False, help="collect 단계 건너뛰기"),
    skip_backtest: bool = typer.Option(False, help="backtest 단계 건너뛰기"),
    skip_report: bool = typer.Option(False, help="report 단계 건너뛰기"),
    skip_export: bool = typer.Option(False, help="export 단계 건너뛰기"),  # NEW
) -> None:
    # ... 기존 collect / analyze / backtest 그대로 ...
    if not skip_export:
        typer.echo("=== Phase 5: export (DuckDB -> JSON for SPA) ===")
        run_step(["export"])
    if not skip_report:
        typer.echo("=== Phase 4: report --latest ===")
        run_step(["report", "--latest"])
    typer.echo("=== Update complete ===")
```

export는 backtest 결과(`backtest_holdings` 포함)와 report 사이에 위치. 이로써 사용자는 `uv run thirteen-f update` 한 번이면 SPA가 즉시 최신 데이터로 동작 (별도 `serve`만 실행하면 됨).

- [ ] **Step 3: e2e 통합 테스트**

```python
# tests/integration/test_export_e2e.py
def test_export_e2e_creates_all_files(test_db_path, tmp_path):
    # 실 DB 사용 (fixture로 small DB)
    result = subprocess.run(
        ["uv", "run", "thirteen-f", "export", "--out", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    
    expected_files = [
        "meta.json", "quarters.json", "quarters_index.json",
        "managers.json", "stocks.json",
        "holdings.json", "holdings_unmapped.json",
        "backtest.json",
    ]
    for f in expected_files:
        assert (tmp_path / f).exists(), f"missing {f}"
    
    # prices 디렉토리에 ticker별 파일
    assert (tmp_path / "prices").is_dir()
    assert len(list((tmp_path / "prices").glob("*.json"))) > 0
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/cli.py src/thirteen_f/cli.py tests/integration/test_export_e2e.py
git commit -m "feat(cli): add 'thirteen-f export' command with e2e test"
```

---

### Chunk B — 정적 서빙 (3 tasks)

#### Task B1: handoff/design → web/static 복사

**Files:**
- Create: `src/thirteen_f/web/static/` (디렉토리 + 파일 9개)
- Add: `.gitignore`에 `src/thirteen_f/web/data/` 추가

- [ ] **Step 1: 파일 복사**

```bash
mkdir -p src/thirteen_f/web/static
cp "handoff/design/13F Terminal.html" src/thirteen_f/web/static/index.html
cp handoff/design/*.css src/thirteen_f/web/static/
cp handoff/design/*.jsx src/thirteen_f/web/static/
cp handoff/design/*.js src/thirteen_f/web/static/
```

- [ ] **Step 2: index.html의 script src 경로 확인 (이미 상대 경로면 OK)**

- [ ] **Step 3: .gitignore 추가**

```
# Web data dump
src/thirteen_f/web/data/
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/static/ .gitignore
git commit -m "feat(web): copy handoff/design to web/static as production assets"
```

---

#### Task B2: server.py FastAPI

**Files:**
- Create: `src/thirteen_f/web/server.py`
- Test: `tests/unit/web/test_server.py`
- Modify: `pyproject.toml` (fastapi, uvicorn 추가)

- [ ] **Step 1: pyproject.toml에 의존성 추가**

```toml
[project]
dependencies = [
    ...,
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
]
```

- [ ] **Step 2: server.py 작성**

**보강 사항 (mount 순서):**
- mount("/", ...)는 catch-all이라 라우터보다 *나중*에 정의해야 `/api/*`가 우선됨 — FastAPI는 mount된 sub-app이 prefix만 매칭하므로 `@app.get("/api/...")`가 먼저 매칭되지만, 안전을 위해 mount는 파일 맨 아래 배치.
- `@app.get("/")` 핸들러 제거. 대신 `StaticFiles(html=True)` 옵션으로 `/` → `index.html` 자동 서빙 (디렉토리 mount 시 표준 동작).
- `DATA_DIR.mkdir(parents=True, exist_ok=True)` 빈 디렉토리 가드 (export 전에 server import만 해도 오류 안 나도록).

```python
# src/thirteen_f/web/server.py
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from thirteen_f.core.config import load_settings

BASE = Path(__file__).parent
STATIC_DIR = BASE / "static"
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # mount target must exist

app = FastAPI(title="13F Terminal", default_response_class=JSONResponse)

class AskRequest(BaseModel):
    question: str
    period: str
    history: list = []

class Card(BaseModel):
    type: str
    title: str
    data: dict

class AskResponse(BaseModel):
    text: str
    cards: list[Card] = []

@app.get("/api/health")
def health():
    settings = load_settings()
    return {"llm_available": bool(settings.google_api_key)}

@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest):
    # Chunk D에서 실연결
    raise HTTPException(503, detail="LLM not configured (Chunk D)")

# mount 순서: 모든 라우트 정의 후에 → catch-all이 라우트보다 우선되지 않도록 보장
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
```

- [ ] **Step 3: 단위 테스트**

```python
# tests/unit/web/test_server.py
from fastapi.testclient import TestClient
from thirteen_f.web.server import app

client = TestClient(app)

def test_health_returns_llm_status():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "llm_available" in r.json()

def test_ask_returns_503_without_llm():
    r = client.post("/api/ask", json={
        "question": "test", "period": "2026-03-31",
    })
    assert r.status_code == 503
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/server.py tests/unit/web/test_server.py pyproject.toml uv.lock
git commit -m "feat(web): FastAPI server with static + /data + /api/health"
```

---

#### Task B3: `thirteen-f serve` CLI + deprecation warning

**Files:**
- Modify: `src/thirteen_f/web/cli.py`
- Modify: `src/thirteen_f/cli.py`
- Test: `tests/integration/test_serve.py`

- [ ] **Step 1: serve 명령 추가**

```python
# src/thirteen_f/web/cli.py
import uvicorn

@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    reload: bool = False,
):
    """Serve 13F Terminal SPA at http://host:port."""
    uvicorn.run(
        "thirteen_f.web.server:app",
        host=host, port=port, reload=reload,
    )
```

- [ ] **Step 2: cli.py dashboard에 deprecation warning**

```python
@app.command()
def dashboard(...):
    typer.echo(
        "⚠️  'dashboard' 명령은 v0.2에서 제거됩니다. 'thirteen-f serve' 사용 권장",
        err=True,
    )
    # 기존 로직 그대로
```

- [ ] **Step 3: 통합 smoke 테스트**

```python
# tests/integration/test_serve.py
import subprocess, time, httpx, signal

def test_serve_starts_and_health_returns_200():
    proc = subprocess.Popen(
        ["uv", "run", "thirteen-f", "serve", "--port", "8766"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        time.sleep(3)
        r = httpx.get("http://127.0.0.1:8766/api/health", timeout=5)
        assert r.status_code == 200
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/cli.py src/thirteen_f/cli.py tests/integration/test_serve.py
git commit -m "feat(cli): add 'thirteen-f serve' + dashboard deprecation warning"
```

---

### Chunk C — 프론트엔드 데이터 연결 (5 tasks)

#### Task C1: hf-data.js bootstrapFromJson

**Files:**
- Modify: `src/thirteen_f/web/static/hf-data.js`

- [ ] **Step 1: Mock 객체를 placeholder로**

```javascript
// hf-data.js 상단
let QUARTERS = [], Q_LABELS = [], STOCKS = [], STOCK_MAP = {};
let MANAGERS = [], MGR_MAP = {}, HOLDINGS = {}, BACKTESTS = [];
let LLM_SUMMARY = {}, META = {};
```

- [ ] **Step 2: bootstrapFromJson 함수**

```javascript
async function bootstrapFromJson(baseUrl = "/data") {
  const [meta, quarters, managers, stocks, holdings, backtests, llm] = await Promise.all([
    fetch(`${baseUrl}/meta.json`).then(r => r.json()),
    fetch(`${baseUrl}/quarters.json`).then(r => r.json()),
    fetch(`${baseUrl}/managers.json`).then(r => r.json()),
    fetch(`${baseUrl}/stocks.json`).then(r => r.json()),
    fetch(`${baseUrl}/holdings.json`).then(r => r.json()),
    fetch(`${baseUrl}/backtest.json`).then(r => r.json()).catch(() => []),
    fetch(`${baseUrl}/llm_summary.json`).then(r => r.json()).catch(() => ({})),
  ]);
  META = meta;
  QUARTERS = quarters.map(q => q.key);
  Q_LABELS = quarters.map(q => q.label);
  STOCKS = stocks;
  STOCK_MAP = Object.fromEntries(STOCKS.map(s => [s.t, s]));
  // pxWeekly는 prices/{ticker}.json에서 lazy fetch
  MANAGERS = managers;
  MGR_MAP = Object.fromEntries(MANAGERS.map(m => [m.id, m]));
  HOLDINGS = holdings;
  BACKTESTS = backtests;
  LLM_SUMMARY = llm;
  Object.assign(window, {
    QUARTERS, Q_LABELS, STOCKS, STOCK_MAP, MANAGERS, MGR_MAP,
    HOLDINGS, BACKTESTS, LLM_SUMMARY, META,
  });
  return META;
}
window.bootstrapFromJson = bootstrapFromJson;
```

- [ ] **Step 3: Commit**

```bash
git add src/thirteen_f/web/static/hf-data.js
git commit -m "feat(frontend): bootstrapFromJson replaces mock data layer"
```

---

#### Task C2: App.jsx loading state + ErrorBoundary

**Files:**
- Modify: `src/thirteen_f/web/static/hf-app.jsx`

- [ ] **Step 1: App 컴포넌트에 loading state 추가**

```jsx
function App() {
  const [bootStatus, setBootStatus] = useState("loading"); // loading|ready|error
  const [bootError, setBootError] = useState(null);
  
  useEffect(() => {
    bootstrapFromJson()
      .then(() => setBootStatus("ready"))
      .catch(e => { setBootError(e); setBootStatus("error"); });
  }, []);
  
  if (bootStatus === "loading") return <LoadingScreen />;
  if (bootStatus === "error") return <ErrorScreen error={bootError} />;
  
  // 기존 router 로직
  ...
}

function LoadingScreen() {
  return <div style={{padding:40, fontFamily:"Pretendard"}}>
    <div className="mono muted">LOADING 13F TERMINAL...</div>
  </div>;
}

function ErrorScreen({error}) {
  return <div style={{padding:40}}>
    <h2>데이터 로드 실패</h2>
    <p className="muted">서버가 켜져 있고 `thirteen-f export`가 실행됐는지 확인하세요.</p>
    <pre>{String(error)}</pre>
  </div>;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/thirteen_f/web/static/hf-app.jsx
git commit -m "feat(frontend): loading/error states for async bootstrap"
```

---

#### Task C3: Screen 데이터 가드

**Files:**
- Modify: 모든 `hf-*.jsx` (dashboard, manager, stock, backtest, compare, misc)

- [ ] **Step 1: 각 Screen 진입 가드**

```jsx
function DashboardScreen({ quarter, setQuarter }) {
  if (!STOCK_MAP || !MGR_MAP) return null;
  // 기존 로직
}
```

- [ ] **Step 2: Stock detail의 daily price lazy fetch**

```jsx
function StockScreen({ ticker, ...}) {
  const [pxDaily, setPxDaily] = useState(null);
  useEffect(() => {
    fetch(`/data/prices/${ticker}.json`)
      .then(r => r.json())
      .then(setPxDaily)
      .catch(() => setPxDaily({date:[], close:[]}));
  }, [ticker]);
  ...
}
```

- [ ] **Step 3: Commit**

```bash
git add src/thirteen_f/web/static/hf-*.jsx
git commit -m "feat(frontend): screen guards + lazy daily price fetch"
```

---

#### Task C4: 헬퍼 검증 + parity 문서

**Files:**
- Create: `_claude_docs/FRONTEND_PARITY.md`
- (Optional) `tests/unit/web/test_parity.py`

- [ ] **Step 1: FRONTEND_PARITY.md 작성 — 어디서 계산되는지 매트릭스**

```markdown
# Frontend ↔ Backend Computation Parity

| 데이터 | 계산 위치 | 검증 방법 |
|---|---|---|
| classifyAction (new/add/cut/exit) | Frontend (hf-data.js) | Python의 signals_quarterly.change_type과 동일 결과 확인 |
| managerPortfolio (weights) | Frontend | holdings × prices 분기말 곱 |
| tickerHolders | Frontend | holdings.json에서 derive |
| spotlight | Frontend | quarterActivity 최대 deltaValue |
| runStrategy (backtest) | Python (engine.py) | Frontend는 backtest.json read-only |
```

- [ ] **Step 2: Commit**

```bash
git add _claude_docs/FRONTEND_PARITY.md
git commit -m "docs: frontend/backend computation parity matrix"
```

---

#### Task C5: tweaks-panel 단순화

**Files:**
- Modify: `src/thirteen_f/web/static/tweaks-panel.jsx`
- Modify: `src/thirteen_f/web/static/hf-app.jsx` (TweaksPanel 호출)

- [ ] **Step 1: host protocol 제거 + density만**

```jsx
// tweaks-panel.jsx
function useTweaks(defaults) {
  const [values, setValues] = React.useState(() => {
    try {
      const stored = localStorage.getItem("hf-tweaks");
      return stored ? {...defaults, ...JSON.parse(stored)} : defaults;
    } catch { return defaults; }
  });
  const setTweak = React.useCallback((key, val) => {
    setValues(prev => {
      const next = {...prev, [key]: val};
      try { localStorage.setItem("hf-tweaks", JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);
  return [values, setTweak];
}

// TweaksPanel: postMessage / message listener 모두 제거
// open state는 button 클릭으로만 토글
function TweaksPanel({ children, title="Tweaks" }) {
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <button className="twk-fab" onClick={() => setOpen(!open)}>⚙</button>
      {open && <div className="twk-panel">...</div>}
    </>
  );
}
```

- [ ] **Step 2: hf-app.jsx의 TweaksPanel 호출에서 accent 컬러/wireframes 버튼 제거**

```jsx
<TweaksPanel>
  <TweakSection label="Layout" />
  <TweakRadio label="Density" value={t.density}
              options={["compact", "regular", "cozy"]}
              onChange={v => setTweak("density", v)} />
</TweaksPanel>
```

- [ ] **Step 3: Commit**

```bash
git add src/thirteen_f/web/static/tweaks-panel.jsx src/thirteen_f/web/static/hf-app.jsx
git commit -m "feat(frontend): simplify tweaks-panel to density only + localStorage"
```

---

### Chunk D — MultiManager + Ask LLM (4 tasks)

#### Task D1: MultiManager 전략 구현

**Files:**
- Create: `src/thirteen_f/backtest/strategies/multi_manager.py`
- Test: `tests/unit/backtest/test_multi_manager.py`

- [ ] **Step 1: TDD — 실패 테스트 먼저**

```python
# tests/unit/backtest/test_multi_manager.py
def test_multi_manager_aggregates_weights():
    strat = MultiManager(mgr_labels=["buffett", "ackman"], top_k=5)
    positions = strat.get_target_positions(date(2026, 3, 31), conn)
    assert len(positions) <= 5
    assert abs(sum(positions.values()) - 1.0) < 0.001
```

- [ ] **Step 2: 구현**

**Lookahead/분기 미스매치 보강:**
- `MAX(period_of_report)` 단독 GROUP BY는 정정본·동일 분기 다중 filing 식별이 불완전. SingleManagerClone과 동일하게 **accession_no까지** latest로 식별 (DuckDB `QUALIFY ROW_NUMBER()` 사용).
- 매니저 A=Q1, B=Q2처럼 분기가 다를 수 있는데 이는 **의도된 동작**: 각 매니저는 as_of_date 시점 자신의 가장 신선한 filing을 사용. SingleManagerClone과 호환되는 lookahead-safe 패턴.
- `form_type LIKE '13F-HR%'`로 13F-NT 제외 (Buffett known issue 회피).

```python
# src/thirteen_f/backtest/strategies/multi_manager.py
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.backtest.strategy import Strategy


class MultiManager(Strategy):
    def __init__(
        self,
        mgr_labels: list[str],
        top_k: int = 15,
        weighting: str = "equal",  # "equal" | "byvalue"
    ) -> None:
        self.mgr_labels = mgr_labels
        self.top_k = top_k
        self.weighting = weighting
        self.name = f"MultiManager({len(mgr_labels)} mgrs, top={top_k})"

    def params_json(self) -> str:
        return json.dumps({
            "mgr_labels": self.mgr_labels,
            "top_k": self.top_k,
            "weighting": self.weighting,
        })

    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        if not self.mgr_labels:
            return {}
        placeholders = ",".join("?" for _ in self.mgr_labels)
        # 각 매니저별 as_of_date 기준 latest accession (lookahead-safe, 13F-HR only)
        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT f.cik, f.accession_no
                FROM filings f
                JOIN managers mg ON mg.cik = f.cik
                WHERE mg.label IN ({placeholders})
                  AND f.filed_at <= ?
                  AND f.superseded_by IS NULL
                  AND f.form_type LIKE '13F-HR%'
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY f.cik
                    ORDER BY f.period_of_report DESC, f.filed_at DESC
                ) = 1
            )
            SELECT m.ticker, SUM(h.value_usd) AS total_value
            FROM holdings h
            JOIN latest l ON l.accession_no = h.accession_no
            JOIN cusip_ticker_map m ON m.cusip = h.cusip
            WHERE m.ticker IS NOT NULL
              AND h.value_usd > 0
            GROUP BY m.ticker
            ORDER BY total_value DESC
            LIMIT ?
            """,
            [*self.mgr_labels, as_of_date, self.top_k],
        ).fetchall()

        if not rows:
            return {}

        if self.weighting == "byvalue":
            total = sum(float(v) for _, v in rows)
            if total <= 0:
                return {}
            return {ticker: float(val) / total for ticker, val in rows}
        # equal-weight (default)
        n = len(rows)
        return {ticker: 1.0 / n for ticker, _ in rows}
```

- [ ] **Step 3: 테스트 pass 확인**

Run: `uv run pytest tests/unit/backtest/test_multi_manager.py -v`

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/backtest/strategies/multi_manager.py tests/unit/backtest/test_multi_manager.py
git commit -m "feat(backtest): MultiManager strategy aggregating multiple managers' top holdings"
```

---

#### Task D2: runner suite/CLI 등록

**Files:**
- Modify: `src/thirteen_f/backtest/runner.py`
- Modify: `src/thirteen_f/cli.py`
- Test: `tests/integration/test_backtest_e2e.py` (확장)

- [ ] **Step 1: default_suite에 MultiManager 추가**

```python
# src/thirteen_f/backtest/runner.py
from .strategies.multi_manager import MultiManager

def default_suite() -> list[Strategy]:
    return [
        SingleManagerClone("buffett"),
        ScoreTopK(top_k=20),
        ConsensusTopK(min_holders=3, top_k=20),
        ConvictionFollow(top_k=10),
        NewBuyOnly(min_holders=2, top_k=15),
        Ensemble({...}),
        MultiManager(mgr_labels=["buffett", "ackman", "tepper"], top_k=15),  # NEW
    ]
```

- [ ] **Step 2: cli.py --strategy MultiManager 옵션 처리**

```python
# src/thirteen_f/cli.py
STRATEGY_MAP = {
    ...,
    "MultiManager": lambda: MultiManager(["buffett", "ackman", "tepper"], 15),
}
```

- [ ] **Step 3: Commit**

```bash
git add src/thirteen_f/backtest/runner.py src/thirteen_f/cli.py tests/integration/test_backtest_e2e.py
git commit -m "feat(backtest): register MultiManager in default suite and CLI"
```

---

#### Task D3: prompts.chat_prompt + summary.chat_reply + ask_context

**Files:**
- Modify: `src/thirteen_f/llm/prompts.py`
- Create: `src/thirteen_f/web/ask_context.py`
- Modify: `src/thirteen_f/llm/summary.py`
- Test: `tests/unit/llm/test_chat.py`

- [ ] **Step 1: prompts.chat_prompt**

```python
# src/thirteen_f/llm/prompts.py
CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["line", "bar", "table"]},
                    "title": {"type": "string"},
                    "data": {"type": "object"},
                },
                "required": ["type", "title", "data"],
            },
        },
    },
    "required": ["text", "cards"],
}

def chat_prompt(question: str, context_block: str) -> str:
    # 길이 제한
    q = (question[:1900] if len(question) > 1900 else question).replace("###", "")
    return f"""당신은 13F 공시 데이터 분석 도우미입니다.
다음 컨텍스트에 기반해 답하세요. 컨텍스트 외 내용은 추측하지 말고 모른다고 답하세요.

⚠️ 모든 답변은 참고용이며 투자 권유가 아닙니다. 13F 공시는 45일 지연·롱 온리·분기 스냅샷의 한계가 있습니다.

### CONTEXT
{context_block}

### USER QUESTION
{q}

### INSTRUCTIONS
- 응답은 반드시 JSON: {{"text": "한국어 답변", "cards": [...]}} 형식
- cards는 0~3개. 종류: line(시계열), bar(분기별 막대), table(랭킹)
- 데이터가 없거나 답할 수 없으면 cards=[] + text에 이유 설명
"""
```

- [ ] **Step 2: ask_context.py**

```python
# src/thirteen_f/web/ask_context.py
import re
from datetime import date

TICKER_RE = re.compile(r'\b[A-Z]{1,5}\b')
MANAGER_KEYWORDS = {
    "buffett": ["buffett", "버핏", "berkshire"],
    "burry": ["burry", "버리"],
    "ackman": ["ackman", "애크먼"],
    # ...
}

def build_context(question: str, period: date, conn) -> str:
    blocks = []
    
    # 1) Quarter summary
    summary = conn.execute("""
        SELECT change_type, COUNT(*) FROM signals_quarterly
        WHERE period_of_report = ? GROUP BY 1
    """, [period]).fetchall()
    blocks.append(f"분기 {period}: " + ", ".join(f"{t}={n}" for t, n in summary))
    
    # 2) 사용자 질문에서 ticker 추출 → 그 종목 데이터
    tickers = TICKER_RE.findall(question.upper())
    for tk in tickers[:3]:
        rows = conn.execute("""
            SELECT m.label, h.shares, h.value_usd
            FROM holdings h
            JOIN filings f ON f.accession_no = h.accession_no
            JOIN managers m ON m.cik = f.cik
            JOIN cusip_ticker_map t ON t.cusip = h.cusip
            WHERE t.ticker = ? AND f.period_of_report = ?
        """, [tk, period]).fetchall()
        if rows:
            blocks.append(f"{tk} 보유: " + ", ".join(f"{l}({s/1e6:.1f}M)" for l, s, _ in rows[:5]))
    
    # 3) 매니저 키워드
    q_lower = question.lower()
    for label, keywords in MANAGER_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            top = conn.execute("""
                SELECT t.ticker, h.value_usd FROM holdings h
                JOIN filings f ON f.accession_no = h.accession_no
                JOIN managers m ON m.cik = f.cik
                LEFT JOIN cusip_ticker_map t ON t.cusip = h.cusip
                WHERE m.label = ? AND f.period_of_report = ?
                ORDER BY h.value_usd DESC LIMIT 10
            """, [label, period]).fetchall()
            blocks.append(f"{label} top10: " + ", ".join(f"{t}" for t, _ in top))
    
    return "\n".join(blocks)
```

- [ ] **Step 3: summary.chat_reply**

```python
# src/thirteen_f/llm/summary.py
import json
from datetime import date
from .gemini import generate
from .prompts import chat_prompt, CHAT_SCHEMA
from thirteen_f.web.ask_context import build_context

def chat_reply(question: str, period: date, conn, api_key: str, model: str) -> dict | None:
    if not api_key:
        return None
    context = build_context(question, period, conn)
    prompt = chat_prompt(question, context)
    raw = generate(
        prompt=prompt, api_key=api_key, model=model,
        max_output_tokens=8192,
        enable_thinking=True,
        response_mime_type="application/json",
        response_schema=CHAT_SCHEMA,
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw, "cards": []}
```

(gemini.generate에 response_mime_type/response_schema 파라미터 추가 필요 — 작은 수정)

- [ ] **Step 4: 단위 테스트**

```python
# tests/unit/llm/test_chat.py
def test_chat_prompt_includes_safety_disclaimer():
    p = chat_prompt("OXY", "context")
    assert "참고용" in p or "투자 권유가 아닙니다" in p

def test_build_context_extracts_tickers(memory_db):
    ctx = build_context("Buffett의 OXY 보유?", date(2026, 3, 31), memory_db)
    assert "OXY" in ctx or "buffett" in ctx
```

- [ ] **Step 5: Commit**

```bash
git add src/thirteen_f/llm/prompts.py src/thirteen_f/llm/summary.py src/thirteen_f/llm/gemini.py src/thirteen_f/web/ask_context.py tests/unit/llm/test_chat.py
git commit -m "feat(llm): chat_reply with JSON schema + ask_context builder"
```

---

#### Task D4: /api/ask 핸들러 + rate limit + 프론트 교체

**Files:**
- Modify: `src/thirteen_f/web/server.py`
- Modify: `src/thirteen_f/web/static/hf-misc.jsx`
- Test: `tests/unit/web/test_server.py` (확장)

- [ ] **Step 1: server.py에 ask 핸들러**

```python
# server.py
from collections import defaultdict
from time import time
from datetime import date

_rate_limit: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_PER_MIN = 10

def _check_rate(ip: str) -> bool:
    now = time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < 60]
    if len(_rate_limit[ip]) >= RATE_LIMIT_PER_MIN:
        return False
    _rate_limit[ip].append(now)
    return True

@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request):
    if not _check_rate(request.client.host):
        raise HTTPException(429, detail="Rate limit exceeded (10/min)")
    
    settings = load_settings()
    if not settings.google_api_key:
        raise HTTPException(503, detail="LLM 비활성화 — GOOGLE_API_KEY 설정 필요")
    
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        period = date.fromisoformat(req.period)
        reply = chat_reply(
            req.question, period, conn,
            settings.google_api_key, settings.google_model,
        )
        if not reply:
            return AskResponse(text="LLM 호출 실패. 잠시 후 재시도하세요.", cards=[])
        return AskResponse(text=reply.get("text", ""), cards=reply.get("cards", []))
    finally:
        conn.close()
```

- [ ] **Step 2: hf-misc.jsx의 send() 함수 — /api/ask fetch로**

```jsx
async function sendAsk(text, period, setThread) {
  setThread(t => [...t, { role: "user", text, ts: Date.now() }]);
  try {
    const r = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: text, period }),
    });
    if (r.status === 503) {
      setThread(t => [...t, { role: "bot", text: "LLM 비활성화 — API 키 설정 후 재시도", ts: Date.now() }]);
      return;
    }
    if (r.status === 429) {
      setThread(t => [...t, { role: "bot", text: "분당 요청 한도 초과. 잠시 후 재시도.", ts: Date.now() }]);
      return;
    }
    const data = await r.json();
    setThread(t => [...t, {
      role: "bot", text: data.text, cards: data.cards, ts: Date.now(),
    }]);
  } catch (e) {
    setThread(t => [...t, { role: "bot", text: "네트워크 오류", ts: Date.now() }]);
  }
}
```

- [ ] **Step 3: 단위 + 통합 테스트**

```python
def test_ask_returns_503_without_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    r = client.post("/api/ask", json={"question": "test", "period": "2026-03-31"})
    assert r.status_code == 503

def test_ask_rate_limit(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    for _ in range(11):
        r = client.post("/api/ask", json={"question": "test", "period": "2026-03-31"})
    assert r.status_code == 429
```

- [ ] **Step 4: Commit**

```bash
git add src/thirteen_f/web/server.py src/thirteen_f/web/static/hf-misc.jsx tests/unit/web/test_server.py
git commit -m "feat(web): /api/ask with rate limit + frontend wire to Gemini"
```

---

### Chunk E — 정리 (3 tasks)

#### Task E1: dashboard 모듈 격리

**Files:**
- Move: `src/thirteen_f/dashboard/` → `src/thirteen_f/_legacy_dashboard/`
- Modify: `src/thirteen_f/cli.py` (dashboard 명령 삭제)
- Test: 영향 없음 확인 (dashboard import는 0개)

- [ ] **Step 1: 디렉토리 이동**

```bash
git mv src/thirteen_f/dashboard src/thirteen_f/_legacy_dashboard
```

- [ ] **Step 2: cli.py에서 dashboard 명령 삭제**

dashboard 명령 함수 전체 제거. import 정리.

- [ ] **Step 3: 단위 테스트 전체 통과 확인**

```bash
uv run pytest tests/unit -q
```

- [ ] **Step 4: Commit**

```bash
git add -u src/thirteen_f/ tests/
git commit -m "refactor: move dashboard/ to _legacy_dashboard/, remove dashboard CLI"
```

---

#### Task E2: pyproject 의존성 정리

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: streamlit/plotly 제거, fastapi 확인**

```toml
[project]
dependencies = [
    "duckdb>=0.10",
    "polars>=0.20",
    "httpx>=0.27",
    "lxml>=5.0",
    "pyyaml>=6.0",
    "typer>=0.12",
    "yfinance>=0.2",
    "rich>=13.0",
    "tenacity>=8.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.5",
    # 제거: streamlit, plotly
]
```

- [ ] **Step 2: uv sync + 단위 테스트 통과**

```bash
uv sync
uv run pytest tests/unit -q
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: remove streamlit/plotly, add fastapi/uvicorn/pydantic dependencies"
```

---

#### Task E3: 문서 갱신

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `_claude_docs/` (필요 시)

- [ ] **Step 1: CLAUDE.md 갱신**

```markdown
## Status (as of 2026-05-22)
- [x] **Phase 5** — Static SPA Migration: Streamlit → FastAPI + 9페이지 정적 SPA + Gemini chat /api/ask + MultiManager 전략 + backtest_holdings 테이블 + cusip_ticker_map sector/industry 컬럼

## Commands
uv run thirteen-f export                    # NEW: DuckDB → JSON dump
uv run thirteen-f serve                     # NEW: http://localhost:8765
uv run thirteen-f update                    # CHANGED: collect→analyze→backtest→export→report (export 자동 통합)
uv run python scripts/supplement_sector.py  # NEW: cusip_ticker_map.sector/industry backfill (1회 or 신규 ticker 추가 시)
```

Known Issues에 backtest_holdings/cusip_ticker_map 마이그레이션 노트 추가.

- [ ] **Step 2: README.md 사용자 가이드**

```markdown
## Run the App

1. 데이터 수집 + 분석 + 백테스트 + JSON dump (한 번에):
   uv run thirteen-f update

2. 정적 서버 (별도 터미널에서):
   uv run thirteen-f serve
   → http://localhost:8765

## 신규 ticker가 추가됐다면 (sector 누락 채우기, 선택):
   uv run python scripts/supplement_sector.py
```

`update`가 export까지 자동 수행하므로 사용자는 별도 `export`를 실행할 필요 없음 (단, JSON만 다시 만들고 싶을 때는 `uv run thirteen-f export` 단독 실행 가능).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md _claude_docs/
git commit -m "docs: update for Phase 5 (static SPA migration)"
```

---

## Critical Files

> **수정 위치 원칙 (보강):** Task B1에서 `handoff/design/`의 정적 자산을 `src/thirteen_f/web/static/`으로 **복사**한 직후부터, 모든 frontend 수정은 **반드시 `src/thirteen_f/web/static/` 쪽에서만** 진행. `handoff/design/`은 디자인 reference로 read-only 보존 (mock 객체와 prototype 단계의 흔적 유지 → 차후 디자인 비교용). 이 원칙으로 Critical Files 경로를 통일.

| 파일 | 역할 |
|---|---|
| `src/thirteen_f/dashboard/tables.py` | SQL helper 재활용 소스 (A1에서 web/queries.py로 이주) |
| `src/thirteen_f/backtest/engine.py` | `_persist_result`에 backtest_holdings INSERT 추가, run_backtest에 `quarter_holdings` snapshot 누적 (A4) |
| `src/thirteen_f/llm/summary.py` | chat_reply 추가 위치 (D3) |
| `src/thirteen_f/cli.py` | serve/export 명령 등록 + dashboard deprecation + update에 export 통합 (A5/B3/D2/E1) |
| `src/thirteen_f/web/static/hf-data.js` | bootstrap 함수 추가 + 헬퍼 그대로 유지 필수 (C1). `handoff/design/`은 read-only reference |
| `src/thirteen_f/web/static/hf-misc.jsx` | scriptedReply → /api/ask fetch 교체 (D4) |
| `src/thirteen_f/web/static/tweaks-panel.jsx` | host protocol 제거, density만 유지 (C5) |
| `scripts/init_db.py` | backtest_holdings 테이블 신설 + cusip_ticker_map에 sector/industry 컬럼 추가 (A3/A4) |
| `scripts/supplement_sector.py` | yfinance로 cusip_ticker_map.sector/industry/name 1회 backfill (A3 신규) |
| `config/managers.yaml` | color 컬럼 추가 (A2) |

## Risks / Known Issues

1. **backtest_holdings 기존 run 데이터 없음** — A4 이후 기존 backtest 결과의 holdingsLog는 비어있음. 사용자에게 `thirteen-f backtest --all` 재실행 권장 (마이그레이션 노트).
2. **CDN 의존(React 18 + Babel-standalone)** — 프로토타입 그대로 유지. Babel runtime 컴파일 ~300ms 비용 감수. 미래에 esbuild 사전 컴파일 고려는 backlog.
3. **prices daily 크기** — ticker별 split로 lazy load 가능. List 페이지는 quarterly만 로드, Stock detail에서만 daily fetch.
4. **avatar/color 매핑** — managers.yaml에 color 컬럼 추가 + avatar는 label 첫 2글자 자동. SECTOR_COLORS와 manager color는 별도 팔레트 (디자인 매핑 유지).
5. **MultiManager 신규** — 7번째 전략. lookahead-safe(SingleManagerClone과 동일 패턴, `QUALIFY ROW_NUMBER()` + `form_type LIKE '13F-HR%'`). 매니저별 분기가 다를 수 있음은 의도된 동작.
6. **호환성** — Chunk B 끝나면 사용자는 `dashboard`와 `serve` 둘 다 가능. Chunk E에서만 dashboard 제거.
7. **cusip_ticker_map.sector backfill 1회 필요** — A3에서 `scripts/supplement_sector.py`를 1회 실행해야 stocks.json의 sector가 채워짐. yfinance rate limit 부담은 16 ticker × 1회라 무시 가능. 신규 ticker 추가 시 재실행.
8. **server.py mount 순서** — `app.mount("/", StaticFiles(html=True))`는 catch-all이라 반드시 모든 `/api/*` 라우트 정의 *후* 호출. `html=True`로 `/` → `index.html` 자동 매핑되어 별도 root 핸들러 불필요.

## Verification

각 chunk 종료 시 다음 검증:

**A 종료**: `uv run pytest tests/unit/web -q` 모두 통과. `uv run python scripts/supplement_sector.py`로 cusip_ticker_map sector backfill 1회 수행. `uv run thirteen-f export` 실행 → `src/thirteen_f/web/data/`에 모든 JSON 파일 생성, schema 검증 pass. `stocks.json`의 sector 값 분포 확인 (단일 "Other" 비율이 50% 이하면 정상).

**B 종료**: `uv run thirteen-f serve` 실행 → `http://127.0.0.1:8765/` 응답 200 (정적 HTML), `/api/health` JSON 응답. dashboard 명령에 deprecation warning 출력.

**C 종료**: 브라우저에서 9 페이지 모두 navigate → console error 0, 데이터 표시 확인 (Playwright-MCP로 manual smoke).

**D 종료**: Ask 페이지에서 "이번 분기 에너지 섹터로 자금 이동" 같은 질문 → Gemini 응답 + 카드 렌더링. API 키 없는 환경에서는 안내 메시지.

**E 종료**: pyproject 의존성에서 streamlit 제거 후 `uv sync` + 전체 단위 테스트 통과. README/CLAUDE.md 안내 정확.

## Commands

```bash
# 전체 파이프라인 (collect → analyze → backtest → export → report)
uv run thirteen-f update

# JSON dump 단독 (DB만 갱신한 뒤 SPA만 새로고침하고 싶을 때)
uv run thirteen-f export

# 정적 서버 부팅
uv run thirteen-f serve --host 127.0.0.1 --port 8765

# 백테스트 재실행 (holdings 정보 채우기, 마이그레이션 1회)
uv run thirteen-f backtest --all --start 2024-01-02

# cusip_ticker_map.sector backfill (Chunk A 진행 후 1회)
uv run python scripts/supplement_sector.py

# 단위 테스트
uv run pytest tests/unit -q  # 119 + 신규 ~20 → 약 139 passed 예상
```

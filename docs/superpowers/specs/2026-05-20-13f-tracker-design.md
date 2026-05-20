# 13F Portfolio Tracker — Design Spec

- **작성일**: 2026-05-20
- **상태**: 디자인 (구현 전)
- **목적**: 13F로 공개되는 미국 투자 거장 15명의 포트폴리오 변화를 추적·분석·시각화하고, 다중 전략 백테스트로 시그널의 정직성을 검증하는 개인용 도구를 만든다.

---

## 1. 개요

13F-HR은 분기말 후 최대 45일 이내에 SEC에 제출되는 보고서로, 미국 상장 주식 운용자산 $100M 이상 기관 매니저의 분기 보유 종목을 공개한다. 본 시스템은 이 데이터를 EDGAR에서 직접 파싱·적재하고, 거장별/컨센서스/종합 점수로 시그널화한 뒤, 다중 전략으로 백테스트하여 그 가치를 정량 검증한다. 결과는 Streamlit 대시보드(평소 탐색)와 Quarto 정적 HTML 리포트(분기 발표 후 1회)로 사용한다.

### 1.1 사용 가치 (균형)

| 가치 | 구현 방식 |
|---|---|
| 시그널 발굴 | Streamlit Overview/Signals 페이지, 종합 점수 랭킹 |
| 정량적 검증 | 6개 등록 전략 동시 백테스트 + 거래비용/Lookahead 가드 |
| 분석/학습 | 거장 상세 페이지, 거장간 비교, Quarto 분기 리포트 |

### 1.2 추적 대상 — 거장 15명

| 스타일 | 인원 | 명단 |
|---|---|---|
| 가치/품질 | 7 | Buffett, Klarman, Akre, Li Lu, Pabrai, Greenblatt, Nygren |
| 액티비스트/이벤트 | 4 | Ackman, Loeb, Einhorn, Icahn |
| 매크로/컨트래리언 | 4 | Tepper, Druckenmiller, Burry, Dalio |

선정 원칙: (1) 13F 시그널 가치 입증, (2) 추종 가능한 미국 상장 주식 비중이 충분히 높음, (3) 스타일 분산. ARK·Renaissance·Tiger Global·Bridgewater(개별 종목 측면) 등은 13F 가치가 약하다고 판단해 제외하거나(Bridgewater의 경우) ETF 시그널 위주로 가중치를 조정.

### 1.3 데이터 범위

- 기간: 2011-01-01 ~ 현재 (약 15년, ~60 분기)
- 예상 데이터량: 약 750~900 필링, holdings 5~6만 행, prices 약 200만 행, DuckDB 파일 1~2 GB

---

## 2. 핵심 결정 요약

| 영역 | 결정 |
|---|---|
| 사용 가치 | 시그널 발굴 + 정량적 검증 + 분석/학습 (균형) |
| 거장 명단 | 15명 (가치 7 / 액티 4 / 매크로 4) |
| 시그널 깊이 | 점수화 — diff + consensus + HHI + Conviction + Continuity + Cloning Quality + 종합 점수 |
| 백테스트 | 다중 전략 비교 + 전략 플러그인 구조 |
| 데이터 범위 | 15년 (~60분기) |
| Phase 순서 | 수집 → 분석 → 백테스트 → 대시보드 |
| 대시보드 | Streamlit + Quarto 하이브리드 (멀티페이지 5 + 분기 리포트) |
| 아키텍처 | 단일 패키지 모듈러 + 자체 백테스트 엔진 + DuckDB 단일 저장소 |
| 가격 데이터 | yfinance 기본 + pandas-datareader(Stooq) fallback |
| 패키지 매니저 | uv |
| Python 의존성 | httpx, lxml, duckdb, polars, pyyaml, python-dotenv, yfinance, pandas-datareader, typer, streamlit, plotly, rich, tenacity |
| 시스템 도구 | Quarto CLI (분기 리포트용) |

---

## 3. 아키텍처 & 패키지 구조

### 3.1 디렉토리

```
13f-tracker/
├── pyproject.toml
├── .env.example                # SEC_USER_AGENT 등
├── README.md
├── config/
│   ├── managers.yaml           # 거장 15명 명단·CIK·메타
│   ├── analysis.toml           # 시그널 threshold·가중치
│   └── scoring.toml            # 종합 점수 컴포넌트 가중치
├── data/                       # ⛔ git 제외
│   ├── 13f.duckdb
│   └── logs/
├── reports/
│   ├── quarto/                 # .qmd 소스
│   │   ├── _quarto.yml
│   │   ├── index.qmd
│   │   ├── 01_overview.qmd
│   │   ├── 02_managers.qmd
│   │   ├── 03_signals.qmd
│   │   ├── 04_backtest.qmd
│   │   ├── 05_data_quality.qmd
│   │   └── _common.py
│   └── output/                 # ⛔ git 제외, quarto render 산출물
│       └── 2026Q1/index.html
├── src/
│   └── thirteen_f/
│       ├── __init__.py
│       ├── cli.py              # typer 진입점
│       ├── core/
│       │   ├── config.py
│       │   ├── logging.py
│       │   └── dates.py        # 분기 ↔ 날짜 변환
│       ├── collect/
│       │   ├── edgar_client.py
│       │   ├── resolve_cik.py
│       │   ├── parser.py
│       │   ├── cusip_mapper.py
│       │   ├── price_loader.py
│       │   └── loader.py
│       ├── analyze/
│       │   ├── diff.py
│       │   ├── consensus.py
│       │   ├── concentration.py
│       │   ├── conviction.py
│       │   ├── continuity.py
│       │   ├── cloning_quality.py
│       │   └── score.py
│       ├── backtest/
│       │   ├── engine.py
│       │   ├── strategy.py     # Strategy ABC
│       │   ├── strategies/
│       │   │   ├── single_manager.py
│       │   │   ├── consensus_top_k.py
│       │   │   ├── score_top_k.py
│       │   │   ├── conviction_follow.py
│       │   │   ├── new_buy_only.py
│       │   │   └── ensemble.py
│       │   ├── metrics.py
│       │   └── runner.py
│       └── dashboard/
│           ├── app.py
│           ├── pages/
│           │   ├── 1_Overview.py
│           │   ├── 2_Manager.py
│           │   ├── 3_Signals.py
│           │   ├── 4_Backtest.py
│           │   └── 5_Compare.py
│           ├── charts.py
│           └── tables.py
├── tests/
│   ├── unit/
│   └── integration/
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-05-20-13f-tracker-design.md
```

### 3.1.1 모듈 간 import 정책

- `pip install -e .` (uv: `uv pip install -e .`)로 `thirteen_f` 패키지 설치 후 사용
- Streamlit 페이지(`dashboard/`)와 Quarto의 `reports/quarto/_common.py` 모두 `from thirteen_f.analyze.score import ...` 형태로 import
- Quarto 렌더 시 jupyter kernel은 동일 venv를 사용하도록 `_quarto.yml`의 `jupyter: python3` 설정 + 가상환경 활성 상태에서 렌더 실행

### 3.2 CLI 진입점

```
thirteen-f collect              # Phase 1: EDGAR 수집 + 가격 다운로드
thirteen-f analyze              # Phase 2: 시그널 점수 계산
thirteen-f backtest --all       # Phase 3: 등록 전략 모두 실행
thirteen-f backtest --strategy ScoreTopK --top-k 20
thirteen-f dashboard            # Phase 4: Streamlit 실행
thirteen-f report --quarter 2026Q1
thirteen-f report --latest --open
thirteen-f update               # collect → analyze → backtest --all → report --latest
```

### 3.3 데이터 흐름

```
EDGAR API ──► parser ──► loader ──► DuckDB(filings, holdings)
                  │                       ▲
                  └─► cusip_mapper ────────┘
                                      
yfinance ──► price_loader ─────────► DuckDB(prices)

DuckDB ─► analyze ──► DuckDB(signals_quarterly, consensus_quarterly, total_scores)

DuckDB ─► backtest ──► DuckDB(backtest_runs, backtest_curves, backtest_metrics)

DuckDB ─► Streamlit 5페이지 (라이브 탐색)
DuckDB ─► Quarto 1 HTML 리포트 (분기 1회)
```

### 3.4 의존성

```toml
[project]
dependencies = [
    "httpx>=0.27",
    "lxml>=5.0",
    "duckdb>=1.0",
    "polars>=1.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "yfinance>=0.2",
    "pandas-datareader>=0.10",
    "typer>=0.12",
    "streamlit>=1.40",
    "plotly>=5.20",
    "rich>=13.0",
    "tenacity>=8.0",
    "jupyter>=1.0",     # Quarto 백엔드
]
[dependency-groups]
dev = ["pytest", "pytest-cov", "ruff", "mypy", "vcr-py"]
```

시스템 도구: **Quarto CLI** (Windows: `winget install RStudio.Quarto`).

---

## 4. 데이터 모델

### 4.1 `config/managers.yaml`

```yaml
- name: "Warren Buffett"
  label: "Buffett"
  cik: "0001067983"
  fund: "Berkshire Hathaway"
  style: "value"            # value | activist | macro
  active_since: 1996
  notes: "13F 추종 원조"
  cloning_score_weight: 1.0
- name: "Ray Dalio"
  label: "Dalio"
  cik: "0001350694"
  fund: "Bridgewater Associates"
  style: "macro"
  active_since: 2011
  notes: "ETF 비중 높음 — 매크로 시그널 위주 해석"
  cloning_score_weight: 0.5
# ... 총 15명
```

### 4.2 DuckDB 스키마 (10개 테이블)

```sql
-- 거장 명단
CREATE TABLE managers (
    cik VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    label VARCHAR,
    fund VARCHAR,
    style VARCHAR,                      -- value | activist | macro
    active_since INTEGER,
    cloning_score_weight DOUBLE DEFAULT 1.0
);

-- 13F 필링
CREATE TABLE filings (
    accession_no VARCHAR PRIMARY KEY,
    cik VARCHAR NOT NULL REFERENCES managers(cik),
    form_type VARCHAR NOT NULL,         -- 13F-HR | 13F-HR/A
    period_of_report DATE NOT NULL,
    filed_at DATE NOT NULL,
    is_amendment BOOLEAN DEFAULT FALSE,
    superseded_by VARCHAR               -- 더 최신 정정본의 accession_no
);

-- 보유 종목
-- ⚠️ put_call은 옵션 미보유 시 NULL이 아니라 빈 문자열 '' 저장 (PK NULL 회피)
-- title_of_class도 동일 정책: 누락 시 빈 문자열 ''
CREATE TABLE holdings (
    accession_no   VARCHAR NOT NULL REFERENCES filings(accession_no),
    cusip          VARCHAR NOT NULL,
    name_of_issuer VARCHAR,
    title_of_class VARCHAR NOT NULL DEFAULT '',
    value_usd      BIGINT,                   -- 항상 달러 단위
    shares         BIGINT,
    share_type     VARCHAR,                  -- SH | PRN
    put_call       VARCHAR NOT NULL DEFAULT '',  -- 'Put' | 'Call' | '' (옵션 미보유)
    PRIMARY KEY (accession_no, cusip, title_of_class, put_call)
);

-- CUSIP → 티커 매핑 캐시
CREATE TABLE cusip_ticker_map (
    cusip VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    figi VARCHAR,
    name VARCHAR,
    is_etf BOOLEAN,
    updated_at TIMESTAMP DEFAULT now()
);

-- 가격 데이터
CREATE TABLE prices (
    ticker VARCHAR,
    date DATE,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    adj_close DOUBLE, volume BIGINT,
    PRIMARY KEY (ticker, date)
);

-- 시그널 (거장×종목×분기)
CREATE TABLE signals_quarterly (
    cik VARCHAR, cusip VARCHAR, period_of_report DATE,
    change_type VARCHAR,                -- new | increase | decrease | exit | hold
    shares_change BIGINT, value_change_usd BIGINT,
    weight_pct DOUBLE,
    conviction_score DOUBLE,            -- 0~1
    continuity_score DOUBLE,            -- 0~1
    PRIMARY KEY (cik, cusip, period_of_report)
);

-- 컨센서스
CREATE TABLE consensus_quarterly (
    period_of_report DATE, cusip VARCHAR,
    ticker VARCHAR,
    holder_count INTEGER,
    new_buy_count INTEGER,
    holder_ciks VARCHAR,                -- comma-separated
    avg_conviction DOUBLE,
    PRIMARY KEY (period_of_report, cusip)
);

-- 종합 점수
CREATE TABLE total_scores (
    period_of_report DATE, cusip VARCHAR,
    ticker VARCHAR,
    consensus_score DOUBLE,
    conviction_score DOUBLE,
    continuity_score DOUBLE,
    cloning_quality_score DOUBLE,
    total_score DOUBLE,
    PRIMARY KEY (period_of_report, cusip)
);

-- 백테스트 실행 메타
CREATE TABLE backtest_runs (
    run_id VARCHAR PRIMARY KEY,
    strategy_name VARCHAR NOT NULL,
    params_json VARCHAR,
    start_date DATE, end_date DATE,
    benchmark VARCHAR DEFAULT 'SPY',
    cost_bps DOUBLE,
    created_at TIMESTAMP DEFAULT now()
);

-- 백테스트 일별 NAV
CREATE TABLE backtest_curves (
    run_id VARCHAR REFERENCES backtest_runs(run_id),
    date DATE, nav DOUBLE, benchmark_nav DOUBLE,
    position_count INTEGER,
    PRIMARY KEY (run_id, date)
);

-- 백테스트 메트릭
CREATE TABLE backtest_metrics (
    run_id VARCHAR PRIMARY KEY REFERENCES backtest_runs(run_id),
    total_return DOUBLE, cagr DOUBLE,
    sharpe DOUBLE, sortino DOUBLE,
    mdd DOUBLE, calmar DOUBLE,
    win_rate_quarterly DOUBLE,
    bench_total_return DOUBLE, bench_cagr DOUBLE
);
```

---

## 5. 수집 파이프라인 (Phase 1)

### 5.1 단계

| 단계 | 모듈 | 책임 |
|---|---|---|
| 1a. EDGAR HTTP | `edgar_client.py` | User-Agent 헤더, rate limit ≤ 8/sec, tenacity 재시도 |
| 1b. CIK 해석 | `resolve_cik.py` | managers.yaml cik=null → company_tickers.json → 검색 폴백 |
| 1c. 필링 추출 | `edgar_client.get_13f_filings` | submissions.recent + files 페이지네이션, form 필터, 정정본 마킹 |
| 1d. info table 파싱 | `parser.py` | lxml local-name(), value 단위 정규화 (filed_at >= 2023-01-03 → 그대로, 미만 → ×1000) |
| 1e. CUSIP 매핑 | `cusip_mapper.py` | DuckDB 캐시 → OpenFIGI 배치 (rate limit 25/min) → fallback ticker=null |
| 1f. 가격 다운로드 | `price_loader.py` | unique ticker → yfinance.download → 실패 시 Stooq → 둘 다 실패는 로그 |
| 1g. DuckDB 적재 | `loader.py` | INSERT OR REPLACE, 거장×분기 단위 트랜잭션, idempotent |

### 5.2 정정본 정책

같은 `(cik, period_of_report)`에 여러 필링이 존재할 때 최신 `filed_at`만 분석/백테스트에 사용. 이전 필링의 `superseded_by` 컬럼에 최신 accession 기록 (감사용 보존).

### 5.3 값 단위 정규화

SEC 2022-09-15 Form 13F 개정안에 따라 2023-01-03 이후 제출분부터 달러 단위. 그 이전 제출분은 천 달러 단위.

```python
# parser.py
def normalize_value(value_str: str, filed_at: date) -> int:
    raw = int(value_str)
    if filed_at < date(2023, 1, 3):
        return raw * 1000
    return raw
```

수집 직후 검증: `mean(value_usd) > 1_000_000` (정규화 누락 자동 감지).

### 5.4 EDGAR 규약

- **User-Agent 필수** (형식: `"Name email@domain.com"`), 누락 시 403
- Rate limit 초당 10건, 안전 마진 8건
- 모든 응답 UTF-8 가정

### 5.5 Ticker=NULL Holdings 처리 정책

CUSIP→티커 매핑이 실패한 행(`cusip_ticker_map.ticker IS NULL`)은 다음과 같이 처리:

| 단계 | 처리 방식 |
|---|---|
| 가격 다운로드 | 자동 스킵 (ticker 없으면 yfinance/Stooq 호출 불가) |
| 분석/시그널 | **포함** — CUSIP을 키로 보존 (`signals_quarterly`, `consensus_quarterly`, `total_scores`는 CUSIP 기준 PK) |
| 백테스트 | **자동 제외** + 남은 종목 weight 재정규화 (∑weight = 1.0 유지) |
| 대시보드/리포트 | CUSIP 노출 + "ticker 미매핑" 배지 표시 |

`failures.jsonl`에 미매핑 CUSIP을 누적 로깅하여 다음 실행 시 OpenFIGI 재시도 가능.

### 5.6 Stooq Fallback Ticker 변환 규칙

`yfinance.download(ticker)` 실패 시 `pandas-datareader.DataReader(stooq_ticker, "stooq")`로 재시도. Stooq는 미국 종목에 `.US` 접미사를 사용:

```python
def to_stooq_ticker(yf_ticker: str) -> str:
    # BRK.B → BRK-B.US, BF.B → BF-B.US (Stooq는 '.' 를 '-'로)
    return yf_ticker.replace(".", "-") + ".US"
```

특수 케이스:
- 클래스주 (`BRK.B`, `BF.B`): `.` → `-` 변환
- ADR/ETF: `.US` 접미사 동일 적용
- 둘 다 실패한 종목은 `failed_tickers.log` 기록, 백테스트에서 영구 제외 (또는 다음 실행 시 재시도)

---

## 6. 분석/시그널 (Phase 2)

### 6.1 시그널 정의

**`diff.change_type`** — 분기간 변화 분류 (threshold 5%, `config/analysis.toml`):

| change_type | 조건 |
|---|---|
| `new` | 직전 분기 미보유, 이번 분기 보유 |
| `increase` | 주식 수 변화 > +5% |
| `decrease` | 주식 수 변화 < -5% |
| `exit` | 직전 분기 보유, 이번 분기 미보유 |
| `hold` | -5% ≤ 변화 ≤ +5% |

**`conviction_score`** — 거장 포트폴리오 내 상대 비중:

```
if portfolio_top_weight == 0:
    conviction_score = 0
elif holding_count_in_portfolio == 1:        # 단일 종목 포트폴리오
    conviction_score = 1.0
else:
    conviction_score = weight_pct / portfolio_top_weight   # 0~1, cap 1.0
```

**`continuity_score`** — 직전 분기까지 이어진 *끊기지 않은* 매집 시퀀스 길이:

```
# 현재 분기 t를 기점으로 거꾸로 직전 4분기 t-1, t-2, t-3, t-4 순회
# change_type ∈ {new, increase, hold} 분기를 카운트하다가
# decrease 또는 exit 만나면 중단 (그 이전 분기는 무시)
continuity_score = (끊기지 않은 매집 분기 수) / 4   # 0~1, cap 1.0

예시:
  t-3=new, t-2=increase, t-1=hold, t=hold    → 4/4 = 1.0
  t-3=new, t-2=increase, t-1=decrease, t=hold → 1/4 = 0.25 (decrease 이전 무시)
  t-1=exit, t=new                              → 1/4 = 0.25
```

명시적 정의: "the most recent unbroken sequence of `change_type ∈ {new, increase, hold}` quarters ending at the current quarter, capped at 4."

**`consensus_score`** — `holder_count / 15` (전체 거장 수 대비).

**`cloning_quality_score`** — 해당 종목을 보유한 거장들의 `cloning_score_weight` **단순 산술 평균** (가중 평균 X). 예: 3명이 보유, weights = [1.0, 1.0, 0.5] → `(1.0 + 1.0 + 0.5) / 3 = 0.83`.

**`total_score`** — 위 4개 컴포넌트의 가중 합 (`config/scoring.toml`):

⚠️ **검증 규칙**: `scoring.toml` 로드 시 `abs(sum(weights.values()) - 1.0) < 0.01` 확인. 차이 발생 시 즉시 에러.

```toml
[weights]
consensus = 0.30
conviction = 0.30
continuity = 0.20
cloning_quality = 0.20
```

### 6.2 컨센서스

같은 분기에 N명 이상이 보유 → `holder_count`, 신규 매수 → `new_buy_count`. 거장 CIK 리스트도 저장 (누가 사는지 추적).

### 6.3 집중도 (HHI)

거장 포트폴리오 단위 `HHI = Σ(weight_pct²)`. 대시보드 거장 상세 페이지 표시용.

---

## 7. 백테스트 엔진 (Phase 3)

### 7.1 Strategy ABC

```python
from abc import ABC, abstractmethod
from datetime import date
import duckdb

class Strategy(ABC):
    name: str

    @abstractmethod
    def get_target_positions(
        self, as_of_date: date, conn: duckdb.DuckDBPyConnection
    ) -> dict[str, float]:
        """as_of_date 시점에 알려진 13F만 보고 (filed_at <= as_of_date)
        목표 보유 비중 ticker -> weight 반환. weight 합은 1.0."""
        ...
```

엔진은 이 인터페이스만 의존 → 새 전략 = 클래스 1개로 추가 가능.

**weight 합 1.0 책임**: Strategy 클래스가 반환 시점에 보장. 엔진은 받은 weight를 그대로 사용하되 단위 테스트(`test_strategy_clone.py` 등)로 `abs(sum(weights) - 1.0) < 1e-6` 검증. ticker=null로 제외되는 종목이 있으면 Strategy 내부에서 재정규화 후 반환.

### 7.2 등록된 전략 6종

| 클래스 | 기본 파라미터 | 설명 |
|---|---|---|
| `SingleManagerClone` | `label='Buffett'` | 특정 거장 최신 13F 그대로 복제, weight = value_usd / 총가치 |
| `ConsensusTopK` | `min_holders=3, top_k=20` | N명 이상 보유 중 종합점수 Top-K, 동일 가중 |
| `ScoreTopK` | `top_k=20` | 종합점수 단순 Top-K, 동일 가중 |
| `ConvictionFollow` | `top_k=10` | 거장별 conviction Top-N 통합, 평균 가중 |
| `NewBuyOnly` | `min_holders=2, top_k=15` | 신규 매수 컨센서스만 (turnover 높음) |
| `Ensemble` | `weights={'SingleManagerClone(Buffett)': 0.4, 'ScoreTopK(20)': 0.4, 'ConsensusTopK(3,20)': 0.2}` | 3 전략 가중 평균, 합 = 1.0 |

### 7.3 엔진 (`engine.py`)

```python
def run_backtest(
    strategy: Strategy,
    start: date, end: date,
    cost_bps: float = 10,            # 매수·매도 각각 적용 (편도 10bp)
    benchmark: str = "SPY",
    initial_capital: float = 1_000_000,
    conn: duckdb.DuckDBPyConnection = ...,
) -> BacktestResult:
    ...
```

**리밸런싱 트리거**: 매 영업일 `strategy.get_target_positions(as_of=today)` 호출. 결과가 직전 포지션과 다르면 그 차이만큼 리밸런싱(부분 거래) + 거래비용 발생. 결과가 같으면 무거래·무비용. 이로써 전략 클래스가 트리거 시점을 자유롭게 결정 (예: `ScoreTopK`는 점수가 갱신될 때마다, `SingleManagerClone(Buffett)`는 Buffett의 새 13F가 도착할 때마다).

**거래비용 정의**:
- `cost_bps`는 **편도**. 즉 매수에 한 번, 매도에 한 번 각각 `cost_bps/10000` 곱한 금액 차감
- 슬리피지 추가 가정 없음 (현실 보수성을 원하면 `cost_bps`를 20~30bp로 상향)
- 배당 처리: `prices.adj_close` 사용으로 배당이 가격에 자동 반영 (별도 cashflow 계산 X)

루프(의사코드):
```
영업일 daily loop:
    target = strategy.get_target_positions(as_of=today, conn)
    if target != current_positions:
        # Σ|Δw|는 매수 weight 총합 + 매도 weight 총합 (=매수·매도 거래량 합)
        # 편도 cost_bps를 곱하면 매수에 한 번, 매도에 한 번 부과한 것과 동등
        trade_value = Σ|target_w - current_w| × portfolio_value
        cost = trade_value × cost_bps / 10000
        portfolio_value -= cost
        current_positions = target
    portfolio_return = Σ(weight × (adj_close_today / adj_close_yesterday - 1))
    nav_today = portfolio_value * (1 + portfolio_return)
    benchmark_nav = ... (SPY adj_close 기반)
```

### 7.4 Lookahead 가드 + period_of_report 사용 규약

`strategy.get_target_positions` 내 모든 SQL은 `WHERE filings.filed_at <= ?` 강제. 단위 테스트(`test_lookahead_guard.py`)로 미래 데이터 누출 시 즉시 실패하도록 검증.

**`period_of_report` 사용 규약**:
- 백테스트 진입 트리거에 `period_of_report` 사용 금지 (lookahead bias 위험)
- 단순 식별·필터 용도 OK: "어떤 분기의 데이터인가" 표시, 분기 grouping
- 즉 `WHERE period_of_report >= X`는 가능하나 `WHERE period_of_report = today`처럼 시점 비교는 금지

### 7.5 메트릭

| 메트릭 | 산식 |
|---|---|
| `total_return` | `nav_end / nav_start - 1` |
| `cagr` | `(nav_end / nav_start) ^ (252 / num_business_days) - 1` |
| `sharpe` | `mean(daily_return) / std(daily_return) × √252` (무위험률 0 가정) |
| `sortino` | `mean(daily_return) / std(daily_return where daily_return < 0) × √252` |
| `mdd` | `max((peak_nav - nav) / peak_nav)` 전 기간 |
| `calmar` | `cagr / mdd` |
| `win_rate_quarterly` | `count(quarter_pnl > 0) / total_quarters`. 분기 PnL = 해당 분기 마지막 영업일 nav / 첫 영업일 nav - 1 (벤치마크 비교 X, 절대 수익률 기준) |

### 7.6 Runner

`runner.run_default_suite()`: 6개 전략을 동일 기간·동일 비용으로 실행, `backtest_runs/curves/metrics` 적재. 대시보드/리포트가 결과를 그대로 읽는다.

---

## 8. 대시보드 (Phase 4)

### 8.1 Streamlit 5페이지 (탐색용)

| 페이지 | 사이드바 | 핵심 컴포넌트 |
|---|---|---|
| `app.py` 홈 | — | 최신 분기 헤드라인, 거장 활동 표 |
| `1_Overview` | 분기 선택 | 컨센서스 매트릭스(거장×종목 히트맵), 변화 워터폴, 신규/청산 리스트 |
| `2_Manager` | 거장 선택 | 분기 추이 라인, 비중 트리맵, 변화 테이블, HHI |
| `3_Signals` | 분기·가중치 슬라이더·min_holders 필터 | 종합 점수 Top-N 테이블, 종목 드릴다운 |
| `4_Backtest` | 전략 다중 선택·기간·비용 | 누적 수익률 곡선, Drawdown 영역, 메트릭 테이블, 분기 히트맵 |
| `5_Compare` | 거장 2~N 다중 선택 | 공통 보유 매트릭스, 섹터 비중 비교, 분기 포트폴리오 cosine 유사도 ※ |

※ **유사도 벡터 정의**: 각 거장의 `weight_pct` 벡터 (해당 분기의 모든 보유 CUSIP 차원, 미보유 CUSIP은 0). 두 거장의 cosine = `dot(v1, v2) / (||v1|| × ||v2||)`. 1.0 = 동일 포트폴리오, 0 = 완전 분리.

데이터 로딩: `@st.cache_data(ttl=600)`, read-only DuckDB 커넥션.

### 8.2 Quarto 분기 리포트 (정적 HTML)

`reports/quarto/` 6개 .qmd 파일을 분기 단위로 렌더 → `reports/output/{YYYY}Q{N}/index.html` 단일 HTML.

| 챕터 | 내용 |
|---|---|
| `index.qmd` | 표지·KPI·핵심 헤드라인 |
| `01_overview.qmd` | 컨센서스 매트릭스, 변화 워터폴 |
| `02_managers.qmd` | 거장 15명별 변화 요약 |
| `03_signals.qmd` | 종합 점수 Top 50 |
| `04_backtest.qmd` | 전략 비교 곡선·메트릭 |
| `05_data_quality.qmd` | 정정본·누락 CUSIP·가격 실패 요약 |

`_common.py`에서 `analyze` 모듈을 import → Streamlit·Quarto 분석 로직 공유. 차트 헬퍼(`dashboard/charts.py`)도 공통.

CLI: `thirteen-f report --latest [--open]`, 내부적으로 `quarto render reports/quarto/ -P quarter=… --output-dir …`.

---

## 9. 데이터 품질·테스트·운영

### 9.1 데이터 품질 가드

**수집 단계 검증** (적재 후 자동):
- `holdings_count > 0`, `sum(value_usd) > 0` (단위 정규화 실패 감지)
- 분기 평균 `value_usd < 10_000` → 단위 변환 누락 의심, 경고
- CUSIP 9자 형식 검증
- 같은 `period_of_report`에 필링 3개 이상 → 알림

**분석 단계 검증**:
- `change_type` 분포 합리성 (`exit` 비율 > 50% → 의심)
- `holder_count > 15` 비정상 검출
- 거장별 `weight_pct` 합 ≈ 1.0 검증

분기 리포트 마지막 페이지(`05_data_quality.qmd`)에 이 메트릭을 모두 시각화.

### 9.2 테스트 전략

```
tests/
├── unit/
│   ├── collect/
│   │   ├── test_parser.py             # 실제 13F XML fixture
│   │   ├── test_value_unit.py         # 2023-01-03 경계 ⭐
│   │   ├── test_amendment_priority.py # 정정본 우선
│   │   └── test_cusip_mapper.py
│   ├── analyze/
│   │   ├── test_diff.py
│   │   ├── test_conviction.py
│   │   ├── test_continuity.py
│   │   └── test_score.py
│   └── backtest/
│       ├── test_lookahead_guard.py    # ⭐ 미래 데이터 누출 차단
│       ├── test_strategy_clone.py
│       ├── test_metrics.py            # 알려진 값으로 샤프/MDD 검증
│       └── test_rebalance.py
└── integration/
    ├── test_collect_pipeline.py        # vcr-py로 EDGAR 응답 녹화
    └── test_backtest_pipeline.py       # synthetic 가격으로 end-to-end
```

**Fixture**: Buffett·Ackman·Tepper의 실제 13F XML 1개씩 저장 → 파서 회귀 방지. EDGAR HTTP는 `vcr-py`로 녹화.

**커버리지 목표**: collect/analyze/backtest 핵심 ≥ 80%. dashboard는 수동 검증.

### 9.3 운영/자동화

**MVP**: 수동 — `thirteen-f update`를 분기 발표 후(~분기말 +50일) 사용자가 직접 실행.

**확장 옵션**: Windows Task Scheduler로 월 1회 자동 → 정정본도 자연스럽게 잡힘.

`thirteen-f update` 통합 명령:
1. collect (EDGAR + CUSIP + 가격)
2. analyze (시그널 점수 재계산)
3. backtest --all (등록 전략 모두 재실행)
4. report --latest (Quarto 리포트 생성)

각 단계 실패 시 명확한 메시지 + 다음 단계 진행 여부 사용자 확인.

**로깅**: `rich` console + `data/logs/{date}.log`, 실패 종목/CUSIP/필링은 `data/logs/failures.jsonl` 누적.

### 9.4 데이터 저장 정책

- DuckDB 파일(`data/13f.duckdb`): git 제외, 백업은 사용자 책임
- `data/logs/`: git 제외
- `reports/output/`: git 제외 (재생성 가능)
- `managers.yaml`: git 커밋 (CIK 해석 결과 보존)

---

## 10. Phase별 Definition of Done

| Phase | DoD |
|---|---|
| 0. 환경 셋업 | `uv sync` 성공, DuckDB 초기화 + 빈 테이블 10개 확인, `.env` 설정 완료 |
| 1. 수집 | 15명 × 60분기 적재, holdings 5만 행 이상, value_usd 평균 > 1M USD(단위 정규화 통과), CUSIP 매핑률 ≥ 90% |
| 2. 분석 | 4개 시그널 + 종합 점수 산출, 임의 분기 1개의 Top 20 종목 합리성 수동 검토 통과 |
| 3. 백테스트 | 6개 등록 전략을 2015~현재 기간으로 동시 실행, SPY와 한 차트에서 비교 가능, Lookahead 가드 단위 테스트 통과 |
| 4. 대시보드 | Streamlit 5페이지 로딩, Quarto 리포트 단일 HTML 생성, 분기 전환 시 데이터 즉시 갱신 |

각 Phase 끝에서 멈추고 DoD 충족 여부를 사용자에게 보고 후 다음 Phase 시작.

---

## 11. 위험 요소와 완화

| 위험 | 영향 | 완화책 |
|---|---|---|
| EDGAR 응답 형식 변경 | 파서 깨짐 | 파서 단위 테스트 + 실제 XML fixture + 명확한 에러 |
| value 단위 변환 누락 | 평가액 1000배 차이 | `test_value_unit.py` 경계 케이스 + 수집 시 자동 검출 |
| OpenFIGI rate limit | CUSIP 매핑 지연 | 캐시 우선, 미스만 호출, 25/min 준수 |
| yfinance 일시 장애 | 가격 누락 | Stooq fallback, 둘 다 실패는 종목 제외 (로그 보존) |
| Lookahead bias 누출 | 백테스트 신뢰성 ↓ | 엔진 SQL `filed_at <= as_of_date` 강제, 단위 테스트로 적극 검증 |
| 정정본 누락 | 후행 시그널 못 잡음 | 매 수집 시 `--lookback-quarters 8`로 정정본 재확인 |
| 13F-CT 비공개 신규 매수 | 시그널 늦음 | 시스템 한계로 인정, 리포트에 명시 |
| 동명 회사 CIK 오해석 | 잘못된 매니저 데이터 | resolve_cik 결과를 yaml에 저장 + 첫 실행 시 사용자 확인 로그 |

---

## 12. 13F 데이터의 구조적 한계 (백테스트 해석 시 반드시 고지)

1. **45일 지연** — 공개 시점엔 포지션이 이미 변했을 수 있음
2. **롱 온리** — 숏/헤지 미공개, 옵션은 일부만 → 진짜 포지션의 단면일 뿐
3. **미국 상장 주식만** — 해외주식·채권·현금·사모·암호화폐 제외
4. **분기 스냅샷** — 분기 중간 매매는 보이지 않음
5. **Confidential Treatment** — 일부 거장은 신규 대량 매수를 분기 동안 비공개로 처리, 정정본으로 후행 공개

대시보드와 분기 리포트의 푸터에 위 한계를 항상 표시.

---

## 부록 A. 기술 메모 (외부 의존성)

### EDGAR 엔드포인트
- 제출 목록: `https://data.sec.gov/submissions/CIK{cik:0>10}.json`
- 필링 인덱스: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json`
- 회사 티커: `https://www.sec.gov/files/company_tickers.json`

### OpenFIGI
- `POST https://api.openfigi.com/v3/mapping`
- 무인증 25 req/min, 키 발급 시 250 req/min
- 입력: `[{"idType": "ID_CUSIP", "idValue": "..."}]` (배치 ≤ 100)

### Quarto
- Windows 설치: `winget install RStudio.Quarto`
- 렌더: `quarto render reports/quarto/ -P quarter=2026Q1 --output-dir reports/output/2026Q1/`

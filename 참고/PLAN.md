# PLAN.md — 13F Portfolio Tracker 구현 계획

> 우선순위(사용자 확정): **수집·저장 → 변화 추적 → 대시보드 → 백테스트**
> 데이터 소스: **EDGAR 직접 파싱(무료)**. 추적 대상: `config/managers.yaml` (약 15명).
> 각 Phase는 독립 실행·검증 가능해야 한다. Phase 완료 시 멈추고 사용자 검토.

---

## Phase 0 — 환경 셋업

- [ ] `uv venv` 후 의존성 설치: `httpx lxml duckdb polars pyyaml python-dotenv`
- [ ] `.env.example` → `.env` 복사, `SEC_USER_AGENT` 설정 (형식: `"이름 email@domain.com"`)
- [ ] `data/13f.duckdb` 초기화 스크립트로 `_claude_docs/schema.md`의 테이블 생성
- **DoD:** `uv run python -c "import duckdb; duckdb.connect('data/13f.duckdb')"` 성공, 빈 테이블 존재

---

## Phase 1 — 수집·저장 파이프라인  ← 최우선

목표: `managers.yaml`의 거장들에 대해 최근 N분기 13F 보유내역을 DuckDB에 적재.

### 1a. EDGAR 클라이언트 — `src/thirteen_f/collect/edgar_client.py`
- [ ] `httpx.Client`에 `User-Agent` 헤더 주입 (없으면 403)
- [ ] 초당 10건 이하 rate limit (간단한 sleep/세마포어로 충분)
- [ ] `get_submissions(cik)` : `https://data.sec.gov/submissions/CIK{cik:0>10}.json` 조회

### 1b. 거장 CIK 해석 — `src/thirteen_f/collect/resolve_cik.py`
- [ ] `managers.yaml`에서 `cik`가 null인 항목만 EDGAR company search로 해석
- [ ] 해석된 CIK는 yaml에 다시 기록 (다음 실행 시 스킵)
- [ ] ⚠️ 동명 회사 주의 — 해석 결과는 로그로 남겨 사용자가 검증 가능하게 한다

### 1c. 13F 필링 목록 추출 — `edgar_client.py`
- [ ] submissions JSON의 `filings.recent`에서 `form == "13F-HR"`만 필터
      (`13F-NT`는 보유내역 없음 → 제외, `13F-HR/A` 정정본은 별도 플래그)
- [ ] 각 필링의 `accessionNumber`, `reportDate`(period_of_report), `filingDate`(filed_at) 수집

### 1d. information table 파싱 — `src/thirteen_f/collect/parser.py`
- [ ] 필링 인덱스(`.../{accession}/index.json`)에서 information table XML 식별
- [ ] `lxml`로 `infoTable` 반복 파싱: nameOfIssuer, titleOfClass, cusip, value,
      shrsOrPrnAmt(sshPrnamt/sshPrnamtType), putCall, votingAuthority
- [ ] ⚠️ **value 단위 함정**: 2023-01-03 이전 필링은 value가 *천 달러* 단위, 이후는 *달러* 단위.
      `period_of_report` 기준으로 정규화하여 DB에는 항상 달러 단위로 저장 (정확한 시점은 edgar_notes.md 참조·검증)

### 1e. CUSIP→티커 매핑 — `src/thirteen_f/collect/cusip_mapper.py`
- [ ] DuckDB `cusip_ticker_map`에서 먼저 조회, 미스만 OpenFIGI API 호출
- [ ] OpenFIGI 결과를 캐시에 적재 (재호출 최소화, rate limit 준수)
- [ ] 매핑 실패 CUSIP은 ticker=null로 두고 로그 (분석 단계에서 CUSIP로 fallback)

### 1f. DuckDB 적재 — `src/thirteen_f/collect/loader.py`
- [ ] `managers`, `filings`, `holdings`, `cusip_ticker_map` 테이블에 upsert
- [ ] 동일 accession 재적재 시 중복 방지 (accession 기준 idempotent)

- **DoD:** 15명 거장의 최근 4~8분기 holdings가 DuckDB에 적재되고,
  `SELECT manager, period, COUNT(*) FROM holdings GROUP BY 1,2` 가 합리적 결과를 반환

---

## Phase 2 — 변화 추적 분석

목표: 분기 간 포지션 변화를 정량화.

### 2a. 분기 diff — `src/thirteen_f/analyze/diff.py`
- [ ] 거장×종목 단위로 `LAG()` 윈도우 → 직전 분기 대비 변화 계산
- [ ] 변화 유형 분류: **신규매수 / 비중확대 / 비중축소 / 전량청산 / 유지**
- [ ] 변화량은 보유 주식 수와 평가액 둘 다로 계산

### 2b. 컨센서스 — `src/thirteen_f/analyze/consensus.py`
- [ ] 같은 분기에 N명 이상이 동시 보유/신규매수한 종목 집계

### 2c. 집중도 — `src/thirteen_f/analyze/concentration.py`
- [ ] 거장별 상위 N 종목 비중, 포트폴리오 HHI

- **DoD:** "이번 분기 신규 매수 Top", "거장 N명 이상 동시 보유" 쿼리가 표로 출력

---

## Phase 3 — Streamlit 대시보드

목표: Phase 1~2 결과를 인터랙티브하게 탐색.

- [ ] `src/thirteen_f/dashboard/app.py` (`streamlit run`)
- [ ] 거장 선택 → 분기별 보유 추이, 변화 테이블(2a 결과)
- [ ] 컨센서스 종목 매트릭스(거장×종목 보유 여부 히트맵)
- [ ] 분기 선택 시 신규 진입/청산 종목 뷰
- **DoD:** 로컬에서 대시보드 구동, 거장 전환 시 데이터 즉시 갱신

---

## Phase 4 — 백테스트 엔진

목표: "거장 따라사기" 전략의 *현실적* 성과 검증.

- [ ] ⚠️ **lookahead bias 차단(가장 중요):** 진입 시점은 `period_of_report`가 아니라
      **`filing_date`(실제 공개일)** 기준. 13F는 분기말 후 최대 45일 지연 공개되므로,
      분기말 가격으로 매수하면 미래 정보를 쓰는 것이 됨.
- [ ] 가격 데이터 소스 결정 (yfinance 등) 후 보유 종목 일간 종가 확보
- [ ] 전략 정의: 예) 특정 거장 포트폴리오를 filing_date에 비중복제, 다음 필링 때 리밸런싱
- [ ] 거래비용·슬리피지 가정 명시
- [ ] 벤치마크(SPY) 대비 누적수익률·MDD·샤프 비교
- **DoD:** lookahead bias 없는 백테스트 곡선과 벤치마크 비교 결과 산출

### 13F 데이터의 구조적 한계 (백테스트 해석 시 반드시 고지)
1. 45일 지연 — 공개 시점엔 포지션이 이미 변했을 수 있음
2. 롱 온리 — 숏/헤지 미공개, 옵션은 일부만 → 진짜 포지션의 단면일 뿐
3. 미국 상장 주식만 — 해외주식·채권·현금·사모 제외
4. 분기 스냅샷 — 분기 중간 매매는 보이지 않음

---

## 진행 규칙
- Phase 내 작업은 위에서 아래 순서로. 한 파일 완성 후 다음 파일.
- 각 Phase 끝에서 멈추고 DoD 충족 여부를 사용자에게 보고.
- 스택/엔드포인트 의문은 `_claude_docs/`를 먼저 갱신한 뒤 구현.

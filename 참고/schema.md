# DuckDB 스키마

> 테이블 정의의 단일 진실 공급원. 스키마 변경은 이 파일을 먼저 고친 뒤 코드 반영.
> DB 파일: `data/13f.duckdb` (커밋 금지).

```sql
-- 추적 대상 거장(매니저)
CREATE TABLE IF NOT EXISTS managers (
    cik           VARCHAR PRIMARY KEY,   -- 10자리 zero-padded
    name          VARCHAR NOT NULL,
    label         VARCHAR                -- 표시용 별칭 (예: "Buffett")
);

-- 13F 필링 단위
CREATE TABLE IF NOT EXISTS filings (
    accession_no      VARCHAR PRIMARY KEY,
    cik               VARCHAR NOT NULL REFERENCES managers(cik),
    form_type         VARCHAR NOT NULL,  -- 13F-HR, 13F-HR/A
    period_of_report  DATE NOT NULL,     -- 분기말 (보고 기준일)
    filed_at          DATE NOT NULL,     -- 실제 공개일 (백테스트 진입 기준)
    is_amendment      BOOLEAN DEFAULT FALSE
);

-- 보유 종목 (필링 × 종목)
CREATE TABLE IF NOT EXISTS holdings (
    accession_no   VARCHAR NOT NULL REFERENCES filings(accession_no),
    cusip          VARCHAR NOT NULL,
    name_of_issuer VARCHAR,
    title_of_class VARCHAR,
    value_usd      BIGINT,               -- 항상 달러 단위로 정규화 저장
    shares         BIGINT,               -- sshPrnamt
    share_type     VARCHAR,              -- SH / PRN
    put_call       VARCHAR,              -- Put / Call / NULL
    PRIMARY KEY (accession_no, cusip, title_of_class, put_call)
);

-- CUSIP → 티커 매핑 캐시
CREATE TABLE IF NOT EXISTS cusip_ticker_map (
    cusip       VARCHAR PRIMARY KEY,
    ticker      VARCHAR,                 -- 매핑 실패 시 NULL
    figi        VARCHAR,
    name        VARCHAR,
    updated_at  TIMESTAMP DEFAULT now()
);
```

## 분석 쿼리 예시 (Phase 2 참고)
```sql
-- 분기 간 변화: 직전 분기 대비 주식 수 증감
SELECT
    m.label,
    h.cusip,
    f.period_of_report,
    h.shares,
    LAG(h.shares) OVER (
        PARTITION BY f.cik, h.cusip ORDER BY f.period_of_report
    ) AS prev_shares
FROM holdings h
JOIN filings  f ON h.accession_no = f.accession_no
JOIN managers m ON f.cik = m.cik;
```

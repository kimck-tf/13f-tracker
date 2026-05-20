# EDGAR / 13F 기술 노트

> 구현 전 반드시 읽을 것. 값이 의심되면 SEC 공식 문서로 재확인.

## 엔드포인트
- 제출 목록(JSON): `https://data.sec.gov/submissions/CIK{cik:0>10}.json`
  - `cik`는 10자리 zero-padding (예: 1067983 → `0001067983`)
  - `filings.recent`에 최근 약 1,000건. 더 과거는 `filings.files`의 추가 JSON을 페이지네이션
  - 주요 필드: `form`, `accessionNumber`, `filingDate`, `reportDate`, `primaryDocument`
- 필링 인덱스: `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/index.json`
  - `{accession_nodash}` = accessionNumber에서 하이픈 제거
  - 여기서 information table XML 파일명을 식별
- 회사 검색(CIK 해석): EDGAR full-text search / company search 활용

## 필수 규약
- **User-Agent 헤더 필수**: 형식 `"Name email@domain.com"`. 누락 시 403.
- **Rate limit 초당 10건**. 안전하게 1초당 8~9건 이하 권장.
- 모든 응답 인코딩 UTF-8 가정.

## 폼 타입
- `13F-HR` : holdings report. **information table 포함** → 주 대상.
- `13F-NT` : notice. 보유내역을 다른 매니저가 보고 → 테이블 없음. 제외.
- `13F-HR/A`, `13F-NT/A` : 정정본. 별도 플래그로 추적(최신 정정본 우선).

## information table XML 구조
루트 `informationTable` 아래 다수의 `infoTable`. 각 항목 주요 태그:
- `nameOfIssuer`, `titleOfClass`, `cusip`
- `value` (평가액)
- `shrsOrPrnAmt` → `sshPrnamt`(수량), `sshPrnamtType`(SH=주식 / PRN=원금)
- `putCall` (옵션일 때만: Put / Call)
- `investmentDiscretion`, `votingAuthority`(Sole/Shared/None)
- 네임스페이스가 붙는 경우가 많으므로 `lxml`에서 local-name() 기반 파싱 권장

## ⚠️ value 단위 변경 (대표적 함정)
- 과거 13F는 `value`를 **천 달러 단위**로 보고했음.
- SEC 개정으로 일정 시점(2023-01-03 전후로 알려짐) 이후 필링은 **달러 단위**로 보고.
- → `period_of_report` 또는 `filing_date` 기준으로 분기하여 DB에는 **항상 달러 단위**로 정규화 저장.
- 정확한 적용 시점/조건은 SEC Form 13F 개정 공지로 반드시 재확인할 것.

## CUSIP → 티커 매핑
- SEC는 CUSIP↔티커 매핑을 직접 제공하지 않음.
- OpenFIGI API(무료, rate limit 있음)로 CUSIP→티커 변환, 결과는 DuckDB에 캐시.
- 매핑 실패분은 ticker=null로 두고 CUSIP를 fallback 키로 사용.

## 백테스트용 시점 (재강조)
- 13F는 분기말 후 **최대 45일** 내 제출 → 공개 지연.
- 백테스트 진입 시점은 반드시 `filing_date` 기준. `period_of_report`로 진입하면 lookahead bias.

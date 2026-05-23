"""Build small context blocks from DuckDB for /api/ask LLM prompts.

Phase 5 D3: 사용자 질문에서 ticker / manager 키워드를 추출해 해당 데이터만 가져와
LLM 컨텍스트로 사용. 전체 holdings를 dump하지 않아 token 비용 ↓·LLM 정확도 ↑.
"""
from __future__ import annotations

import re
from datetime import date

import duckdb

# 2~5자 대문자 — US 티커 일반 길이. 1자 ticker는 false positive 비용이 너무 커서 제외
# (예: "A is good"에서 "A"가 Agilent로 잡힘).
TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")

# 흔한 영문 약어 stop-list — 사용자 질문에 ticker가 아닌 단어로 자주 등장
_TICKER_STOPWORDS = frozenset({
    # 자료 형식 / 일반 약어
    "JSON", "API", "URL", "HTML", "CSS", "PDF", "CSV", "XML", "YAML", "SQL",
    "OK", "USD", "EUR", "JPY", "KRW", "GBP", "CNY", "ETF",
    # 13F 도메인 약어
    "CIK", "SEC", "13F", "13D", "CUSIP", "EDGAR", "NPORT",
    # 직책 / 일반
    "CEO", "CFO", "CTO", "COO", "IPO", "EPS", "PER", "PBR", "ROE", "ROA",
    "Q1", "Q2", "Q3", "Q4", "YTD", "YOY", "QOQ", "MOM", "MTD",
    # 매니저 관련 풀네임 약어
    "WB", "MB", "BA", "SK", "DT", "SD",  # avatar codes
    # 모듈 식별자
    "LLM", "AI", "ML", "GPT",
})


def _candidate_tickers(question_upper: str, known_tickers: frozenset[str]) -> list[str]:
    """Question에서 ticker 후보 추출: 정규식 → stop-list 제거 → known set intersect.

    known_tickers 인자가 비어 있으면 stop-list만 적용 (호환성 fallback).
    """
    seen: set[str] = set()
    out: list[str] = []
    for tk in TICKER_RE.findall(question_upper):
        if tk in _TICKER_STOPWORDS or tk in seen:
            continue
        if known_tickers and tk not in known_tickers:
            continue
        seen.add(tk)
        out.append(tk)
    return out

# 매니저 라벨 → 키워드 (영문 last name + 한글 + 펀드명)
# 라벨은 managers.yaml 그대로 (대소문자 보존)
MANAGER_KEYWORDS: dict[str, list[str]] = {
    "Buffett": ["buffett", "버핏", "berkshire"],
    "Burry": ["burry", "버리", "scion"],
    "Ackman": ["ackman", "애크먼", "pershing"],
    "Klarman": ["klarman", "클라먼", "baupost"],
    "Tepper": ["tepper", "테퍼", "appaloosa"],
    "Druckenmiller": ["druckenmiller", "드러큰밀러", "duquesne"],
    "Akre": ["akre"],
    "LiLu": ["li lu", "리 루"],
    "Pabrai": ["pabrai", "파브라이"],
    "Greenblatt": ["greenblatt", "그린블랫"],
    "Nygren": ["nygren", "오크마크", "oakmark"],
    "Loeb": ["loeb", "third point"],
    "Einhorn": ["einhorn", "greenlight"],
    "Icahn": ["icahn"],
    "Dalio": ["dalio", "bridgewater", "달리오"],
}


def build_context(question: str, period: date, conn: duckdb.DuckDBPyConnection) -> str:
    """Compose a small context block for LLM consumption.

    Returns multi-line string with up to 3 sections:
    1) 분기 변화 분포 (change_type counts)
    2) 질문에 포함된 ticker별 보유자 top 5
    3) 질문에 포함된 매니저별 top 10 보유 종목
    """
    blocks: list[str] = []

    # 1) Quarter change_type distribution
    summary = conn.execute(
        """
        SELECT change_type, COUNT(*) FROM signals_quarterly
        WHERE period_of_report = ?
        GROUP BY change_type
        """,
        [period],
    ).fetchall()
    if summary:
        blocks.append(
            f"분기 {period} 변화 분포: "
            + ", ".join(f"{t}={n}" for t, n in summary if t is not None)
        )

    # 2) Tickers in question → top holders (known set intersect로 false positive 차단)
    known = frozenset(
        t for (t,) in conn.execute(
            "SELECT DISTINCT ticker FROM cusip_ticker_map WHERE ticker IS NOT NULL"
        ).fetchall()
    )
    for tk in _candidate_tickers(question.upper(), known)[:3]:
        rows = conn.execute(
            """
            SELECT m.label, h.shares, h.value_usd
            FROM holdings h
            JOIN filings f ON f.accession_no = h.accession_no
            JOIN managers m ON m.cik = f.cik
            JOIN cusip_ticker_map t ON t.cusip = h.cusip
            WHERE t.ticker = ?
              AND f.period_of_report = ?
              AND f.superseded_by IS NULL
            ORDER BY h.value_usd DESC NULLS LAST
            LIMIT 5
            """,
            [tk, period],
        ).fetchall()
        if rows:
            blocks.append(
                f"{tk} 보유 매니저(top5): "
                + ", ".join(
                    f"{label}({(shares or 0)/1e6:.2f}M, ${(val or 0)/1e6:.0f}M)"
                    for label, shares, val in rows
                )
            )

    # 3) Manager keyword hits → top holdings
    q_lower = question.lower()
    managers_seen: set[str] = set()
    for label, keywords in MANAGER_KEYWORDS.items():
        if label in managers_seen:
            continue
        if any(kw in q_lower for kw in keywords):
            managers_seen.add(label)
            top = conn.execute(
                """
                SELECT t.ticker, h.value_usd
                FROM holdings h
                JOIN filings f ON f.accession_no = h.accession_no
                JOIN managers m ON m.cik = f.cik
                LEFT JOIN cusip_ticker_map t ON t.cusip = h.cusip
                WHERE m.label = ?
                  AND f.period_of_report = ?
                  AND f.superseded_by IS NULL
                  AND t.ticker IS NOT NULL
                ORDER BY h.value_usd DESC NULLS LAST
                LIMIT 10
                """,
                [label, period],
            ).fetchall()
            if top:
                blocks.append(
                    f"{label} top10 보유: "
                    + ", ".join(t for t, _ in top)
                )

    return "\n".join(blocks) if blocks else "관련 데이터 없음."

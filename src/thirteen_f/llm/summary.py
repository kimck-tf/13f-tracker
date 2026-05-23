"""DB → prompt → Gemini 호출 통합 함수. Quarto/Streamlit/CLI에서 공용."""
from __future__ import annotations

import json
from datetime import date

import duckdb

from thirteen_f.llm.gemini import generate
from thirteen_f.llm.prompts import (
    CHAT_SCHEMA,
    chat_prompt,
    quarterly_headline_prompt,
    signal_explain_prompt,
)


def fetch_quarter_context(
    conn: duckdb.DuckDBPyConnection, period: date
) -> dict:
    """헤드라인 요약 용 데이터 fetch."""
    n_holdings = conn.execute(
        "SELECT COUNT(*) FROM holdings h "
        "JOIN filings f ON h.accession_no = f.accession_no "
        "WHERE f.period_of_report = ? AND f.superseded_by IS NULL",
        (period,),
    ).fetchone()[0]
    n_managers = conn.execute(
        "SELECT COUNT(DISTINCT cik) FROM filings "
        "WHERE period_of_report = ? AND superseded_by IS NULL",
        (period,),
    ).fetchone()[0]
    top_tickers = conn.execute(
        "SELECT ticker, total_score FROM total_scores "
        "WHERE period_of_report = ? AND ticker IS NOT NULL "
        "ORDER BY total_score DESC NULLS LAST LIMIT 5",
        (period,),
    ).fetchall()
    change_counts = dict(conn.execute(
        "SELECT change_type, COUNT(*) FROM signals_quarterly "
        "WHERE period_of_report = ? GROUP BY 1",
        (period,),
    ).fetchall())
    new_buy_top = conn.execute(
        "SELECT ticker, new_buy_count, holder_count "
        "FROM consensus_quarterly "
        "WHERE period_of_report = ? AND new_buy_count >= 1 AND ticker IS NOT NULL "
        "ORDER BY new_buy_count DESC, holder_count DESC LIMIT 5",
        (period,),
    ).fetchall()
    return {
        "period": str(period),
        "n_managers": n_managers,
        "n_holdings": n_holdings,
        "top_tickers": top_tickers,
        "change_counts": change_counts,
        "new_buy_top": new_buy_top,
    }


def fetch_top_signals(
    conn: duckdb.DuckDBPyConnection, period: date, top_n: int = 10
) -> list[dict]:
    """시그널 해석 용 Top N 종목 fetch."""
    rows = conn.execute(
        """
        SELECT t.ticker, t.total_score,
               t.consensus_score, t.conviction_score,
               t.continuity_score, t.cloning_quality_score,
               c.holder_count, c.new_buy_count
        FROM total_scores t
        JOIN consensus_quarterly c
          ON c.period_of_report = t.period_of_report AND c.cusip = t.cusip
        WHERE t.period_of_report = ? AND t.ticker IS NOT NULL
        ORDER BY t.total_score DESC NULLS LAST
        LIMIT ?
        """,
        (period, top_n),
    ).fetchall()
    cols = ["ticker", "total_score", "consensus_score", "conviction_score",
            "continuity_score", "cloning_quality_score",
            "holder_count", "new_buy_count"]
    return [dict(zip(cols, r)) for r in rows]


def headline_summary(
    conn: duckdb.DuckDBPyConnection,
    period: date,
    api_key: str,
    model: str = "gemini-2.5-flash",
    enable_thinking: bool = True,
) -> str | None:
    """분기 헤드라인 요약. API 키 없으면 None.

    thinking ON일 때 thinking 토큰이 응답 한도를 함께 쓰므로 max_output_tokens를
    4096으로 충분히 잡는다. thinking OFF는 같은 한도로 응답이 더 빠르게 끝남.
    """
    if not api_key:
        return None
    ctx = fetch_quarter_context(conn, period)
    prompt = quarterly_headline_prompt(
        period=ctx["period"],
        n_managers=ctx["n_managers"],
        n_holdings=ctx["n_holdings"],
        top_tickers=ctx["top_tickers"],
        change_counts=ctx["change_counts"],
        new_buy_top=ctx["new_buy_top"],
    )
    return generate(
        prompt, api_key=api_key, model=model,
        max_output_tokens=4096, enable_thinking=enable_thinking,
    )


def explain_top_signals(  # noqa: D401
    conn: duckdb.DuckDBPyConnection,
    period: date,
    api_key: str,
    top_n: int = 10,
    model: str = "gemini-2.5-flash",
    enable_thinking: bool = True,
) -> str | None:
    """Top N 종목 시그널 해석. API 키 없으면 None.

    Top N 종목별 1-2문장 해석 → thinking ON 시 thinking ~1-2k + 응답 ~500 토큰 위해 8192.
    """
    if not api_key:
        return None
    rows = fetch_top_signals(conn, period, top_n=top_n)
    if not rows:
        return None
    prompt = signal_explain_prompt(period=str(period), rows=rows)
    return generate(
        prompt, api_key=api_key, model=model,
        max_output_tokens=8192, enable_thinking=enable_thinking,
    )


def chat_reply(
    question: str,
    period: date,
    conn: duckdb.DuckDBPyConnection,
    api_key: str,
    model: str = "gemini-2.5-flash",
    enable_thinking: bool = True,
) -> dict | None:
    """Phase 5 D3: /api/ask 응답. structured JSON (text + cards)을 dict로 반환.

    실패 흐름:
    - api_key 비어있음 → None (caller가 503 응답)
    - LLM 호출 실패 → None
    - JSON 파싱 실패 → text-only fallback (cards=[])
    """
    if not api_key:
        return None
    from thirteen_f.web.ask_context import build_context

    context = build_context(question, period, conn)
    prompt = chat_prompt(question, context)
    raw = generate(
        prompt=prompt,
        api_key=api_key,
        model=model,
        max_output_tokens=8192,
        enable_thinking=enable_thinking,
        response_mime_type="application/json",
        response_schema=CHAT_SCHEMA,
    )
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"text": raw, "cards": []}

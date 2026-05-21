"""LLM 보조 모듈 — Gemini API로 분기 리포트 요약 + 시그널 해석.

Plan 작성 시점에 명시적 task 누락되어 별도 보완.
모든 함수는 API 키 미설정 시 None 반환 (graceful skip).
"""
from thirteen_f.llm.gemini import generate
from thirteen_f.llm.summary import (
    headline_summary,
    explain_top_signals,
    fetch_quarter_context,
    fetch_top_signals,
)

__all__ = [
    "generate",
    "headline_summary",
    "explain_top_signals",
    "fetch_quarter_context",
    "fetch_top_signals",
]

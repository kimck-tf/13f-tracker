"""Gemini API thin wrapper using httpx.

`google-genai` SDK 대신 raw HTTP로 호출 — 의존성 추가 회피.
GOOGLE_API_KEY 미설정 시 즉시 None 반환 (시끄러운 에러 X).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def generate(
    prompt: str,
    api_key: str,
    model: str = "gemini-2.5-flash",
    temperature: float = 0.2,
    max_output_tokens: int = 2048,
    timeout: float = 60.0,
    disable_thinking: bool = True,
) -> str | None:
    """Gemini generateContent 1회 호출. 키 없거나 실패 시 None.

    `gemini-3-flash-preview` 같은 thinking 모델은 max_output_tokens를 thinking에 먼저
    소진해 응답 텍스트가 잘릴 수 있음. `disable_thinking=True` (기본)로 thinkingBudget=0
    설정하여 thinking 비활성화. thinking을 지원하지 않는 모델에는 무해.

    Returns:
        모델 응답 텍스트 (한국어 prompt이면 한국어 출력). 실패 시 None.
    """
    if not api_key:
        return None
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    gen_cfg: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if disable_thinking:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }
    try:
        resp = httpx.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(
                "Gemini API non-200: %s — %s", resp.status_code, resp.text[:200]
            )
            return None
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            logger.warning("Gemini response without candidates: %s", str(data)[:200])
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        text = "".join(text_parts).strip()
        return text or None
    except Exception as e:
        logger.warning("Gemini call failed: %s", e)
        return None

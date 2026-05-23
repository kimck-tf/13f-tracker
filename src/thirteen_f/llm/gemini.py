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
    max_output_tokens: int = 8192,
    timeout: float = 60.0,
    enable_thinking: bool = True,
    response_mime_type: str | None = None,
    response_schema: dict | None = None,
) -> str | None:
    """Gemini generateContent 1회 호출. 키 없거나 실패 시 None.

    Args:
        enable_thinking: thinking 모델(예: `gemini-3-flash-preview`)에 대한 toggle.
            True(기본) — 모델 default thinking 사용 (응답 품질 ↑, 토큰·지연 ↑).
            False — `thinkingConfig.thinkingBudget=0` 으로 thinking 비활성화 (지연·비용 ↓).
            thinking 미지원 모델에는 양쪽 모두 무해.
        max_output_tokens: thinking ON일 때 thinking+응답이 함께 나눠 쓰므로 한도를 크게
            잡아야 답변이 잘리지 않는다. 기본 8192 — thinking 2~3k + 응답 1~2k 여유.
        response_mime_type: "application/json" 지정 시 structured output 모드 (Phase 5 D3).
        response_schema: JSON schema 객체. response_mime_type=application/json과 함께 사용.

    Returns:
        모델 응답 텍스트 (한국어 prompt이면 한국어 출력). 실패 시 None.
        structured JSON 모드에서는 JSON 문자열 그대로 반환 — 호출자가 json.loads 해야 함.
    """
    if not api_key:
        return None
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    gen_cfg: dict[str, Any] = {
        "temperature": temperature,
        "maxOutputTokens": max_output_tokens,
    }
    if not enable_thinking:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    if response_mime_type:
        gen_cfg["responseMimeType"] = response_mime_type
    if response_schema:
        gen_cfg["responseSchema"] = response_schema
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

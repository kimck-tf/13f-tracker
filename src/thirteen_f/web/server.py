"""FastAPI server — static SPA + JSON data dump + /api/ask LLM proxy (Phase 5).

Routes:
- ``GET /api/health``       → ``{"llm_available": bool}``
- ``POST /api/ask``         → Gemini chat reply (structured JSON {text, cards})
- ``GET /``                 → ``static/index.html`` (via StaticFiles html=True)
- ``GET /<asset>``          → static asset (hf-*.jsx, .css, etc.)
- ``GET /data/<json>``      → exporter output

Mount order matters: ``StaticFiles(html=True)`` mounted at ``/`` is a catch-all,
so every ``@app.<verb>("/api/...")`` route MUST be defined *before* the mount.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from time import time

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from thirteen_f.core.config import load_settings

BASE = Path(__file__).parent
STATIC_DIR = BASE / "static"
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # mount target must exist

RATE_LIMIT_PER_MIN = 10
_rate_limit: dict[str, list[float]] = defaultdict(list)


def _check_rate(ip: str) -> bool:
    now = time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < 60]
    if len(_rate_limit[ip]) >= RATE_LIMIT_PER_MIN:
        return False
    _rate_limit[ip].append(now)
    return True


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


app = FastAPI(title="13F Terminal", default_response_class=JSONResponse)


@app.get("/api/health")
def health() -> dict:
    settings = load_settings()
    return {"llm_available": bool(settings.google_api_key)}


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, request: Request) -> AskResponse:
    """Phase 5 D4: Gemini chat with structured JSON cards + per-IP rate limit."""
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(client_ip):
        raise HTTPException(429, detail="Rate limit exceeded (10/min)")

    settings = load_settings()
    if not settings.google_api_key:
        raise HTTPException(503, detail="LLM disabled — GOOGLE_API_KEY 미설정")

    try:
        period = date.fromisoformat(req.period)
    except ValueError:
        raise HTTPException(400, detail=f"Invalid period (expected YYYY-MM-DD): {req.period}")

    from thirteen_f.llm.summary import chat_reply

    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    try:
        reply = chat_reply(
            question=req.question,
            period=period,
            conn=conn,
            api_key=settings.google_api_key,
            model=settings.google_model,
            enable_thinking=settings.gemini_thinking,
        )
        if not reply:
            return AskResponse(text="LLM 호출 실패. 잠시 후 재시도하세요.", cards=[])
        return AskResponse(text=reply.get("text", ""), cards=reply.get("cards", []))
    finally:
        conn.close()


# mount: 모든 라우트 정의 후 → catch-all이 /api/* 보다 뒤로 배치
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

"""FastAPI server — static SPA + JSON data dump + /api/ask LLM proxy (Phase 5).

Routes:
- ``GET /api/health``       → ``{"llm_available": bool}``
- ``POST /api/ask``         → Gemini chat reply (wired in Chunk D)
- ``GET /``                 → ``static/index.html`` (via StaticFiles html=True)
- ``GET /<asset>``          → static asset (hf-*.jsx, .css, etc.)
- ``GET /data/<json>``      → exporter output

Mount order matters: ``StaticFiles(html=True)`` mounted at ``/`` is a catch-all,
so every ``@app.<verb>("/api/...")`` route MUST be defined *before* the mount.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from thirteen_f.core.config import load_settings

BASE = Path(__file__).parent
STATIC_DIR = BASE / "static"
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # mount target must exist


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
def ask(req: AskRequest) -> AskResponse:
    # Chunk D에서 실연결
    raise HTTPException(503, detail="LLM not configured (Chunk D)")


# mount: 모든 라우트 정의 후 → catch-all이 /api/* 보다 뒤로 배치
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

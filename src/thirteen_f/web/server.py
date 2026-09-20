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

import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from time import time

import duckdb
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.types import Scope

from thirteen_f.core.config import load_settings

BASE = Path(__file__).parent
STATIC_DIR = BASE / "static"
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)  # mount target must exist

RATE_LIMIT_PER_MIN = 10
# In-memory per-IP rate limit. **Single uvicorn worker만 안전** — multi-worker로 띄우면
# 각 worker가 독립 dict를 가져 effective rate가 N×RATE_LIMIT_PER_MIN이 됨. 진짜 multi-worker
# 환경이 필요하면 slowapi/Redis 같은 외부 store 사용 권장.
# 프록시(Nginx/Cloudflare) 뒤에서는 모두 같은 upstream IP로 보이니 X-Forwarded-For 헤더
# 처리 필요 — 현 구현은 single-process + 직접 노출 가정.
_rate_limit: dict[str, list[float]] = defaultdict(list)


def _check_rate(ip: str) -> bool:
    now = time()
    bucket = [t for t in _rate_limit[ip] if now - t < 60]
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        _rate_limit[ip] = bucket  # 빈 entry는 아래에서 정리
        return False
    bucket.append(now)
    _rate_limit[ip] = bucket
    # 빈 entry 제거 + 다른 IP의 만료 entry도 함께 GC (10 호출당 1회 housekeeping)
    if len(_rate_limit) > 100 or (len(bucket) % 10 == 0):
        for k in list(_rate_limit.keys()):
            _rate_limit[k] = [t for t in _rate_limit[k] if now - t < 60]
            if not _rate_limit[k]:
                del _rate_limit[k]
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

# index.html의 로컬 asset 주소(hf-*.jsx, hf-styles.css)에 붙일 버전 — `href="x.css"` / `src="x.jsx"`
_LOCAL_ASSET_RE = re.compile(r'(?P<attr>href|src)="(?P<path>[^":/][^":]*\.(?:jsx?|css))"')


def asset_version() -> str:
    """static/ 안 파일들의 최신 수정 시각 → 8자리 hex.

    브라우저가 ``Cache-Control: no-cache`` 이전에 받아 둔 사본을 자체 판단으로 계속 쓰는 일을
    막는다(주소가 달라지면 캐시가 무시된다). 파일이 바뀌면 버전이 바뀌고, index.html 자체는
    no-cache라 매번 재검증되므로 새 주소가 바로 전달된다.
    """
    mtime = max((p.stat().st_mtime for p in STATIC_DIR.glob("*.*")), default=0.0)
    return f"{int(mtime):08x}"


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """SPA 진입점. 로컬 asset 주소에 ``?v=<version>``을 붙여 내보낸다 (CDN 주소는 그대로)."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    version = asset_version()
    body = _LOCAL_ASSET_RE.sub(
        lambda m: f'{m.group("attr")}="{m.group("path")}?v={version}"', html
    )
    return HTMLResponse(body, headers={"Cache-Control": "no-cache"})


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


class NoCacheStaticFiles(StaticFiles):
    """매 요청 재검증(``Cache-Control: no-cache``)하는 StaticFiles.

    헤더가 없으면 브라우저가 Last-Modified로 캐시 수명을 추정해, 수정한 .jsx·.css나 export로
    갱신한 JSON 대신 캐시된 예전 파일을 새로고침 후에도 쓴다. no-cache면 매번 ETag로
    재검증하므로 바뀌지 않은 파일은 304로 끝난다.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# mount: 모든 라우트 정의 후 → catch-all이 /api/* 보다 뒤로 배치
app.mount("/data", NoCacheStaticFiles(directory=DATA_DIR), name="data")
app.mount("/", NoCacheStaticFiles(directory=STATIC_DIR, html=True), name="static")

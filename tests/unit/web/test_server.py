"""Unit tests for web/server.py — verify routes + mount order via TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 server 테스트가 load_settings()를 통과하도록 SEC_USER_AGENT 보장."""
    monkeypatch.setenv("SEC_USER_AGENT", "test agent")


@pytest.fixture
def client() -> TestClient:
    from thirteen_f.web.server import app
    return TestClient(app)


def test_health_returns_llm_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "llm_available" in r.json()
    assert r.json()["llm_available"] is False


def test_health_reports_true_when_key_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    r = client.get("/api/health")
    assert r.json()["llm_available"] is True


def test_ask_returns_503_without_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    r = client.post(
        "/api/ask",
        json={"question": "test", "period": "2026-03-31"},
    )
    assert r.status_code == 503


def test_ask_returns_400_for_invalid_period(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    r = client.post(
        "/api/ask",
        json={"question": "test", "period": "not-a-date"},
    )
    assert r.status_code == 400


def test_ask_rate_limit_kicks_in_after_10(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """rate_limit 모듈 변수 reset 후 11번째 요청은 429."""
    from thirteen_f.web import server as srv

    srv._rate_limit.clear()
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    # 유효 DB를 가리키도록 (chat_reply가 DB 연결 시도 → 실패해도 rate 카운팅은 먼저)
    db_path = tmp_path / "rl.duckdb"
    from scripts.init_db import init_db
    init_db(db_path)
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    # chat_reply를 가짜로 — Gemini 호출 안 함
    monkeypatch.setattr(
        "thirteen_f.llm.summary.chat_reply",
        lambda **kwargs: {"text": "ok", "cards": []},
    )
    for i in range(10):
        r = client.post("/api/ask", json={"question": f"q{i}", "period": "2024-03-31"})
        assert r.status_code == 200, f"req #{i+1} got {r.status_code}: {r.text}"
    r = client.post("/api/ask", json={"question": "qLast", "period": "2024-03-31"})
    assert r.status_code == 429


def test_ask_returns_text_and_cards_on_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from thirteen_f.web import server as srv
    from scripts.init_db import init_db

    srv._rate_limit.clear()
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")
    db_path = tmp_path / "ok.duckdb"
    init_db(db_path)
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))
    monkeypatch.setattr(
        "thirteen_f.llm.summary.chat_reply",
        lambda **kwargs: {
            "text": "Buffett은 OXY를 보유 중입니다.",
            "cards": [{"type": "table", "title": "Holders", "data": {"rows": []}}],
        },
    )
    r = client.post("/api/ask", json={"question": "Buffett의 OXY?", "period": "2024-03-31"})
    assert r.status_code == 200
    data = r.json()
    assert "Buffett" in data["text"]
    assert len(data["cards"]) == 1
    assert data["cards"][0]["title"] == "Holders"


def test_root_serves_static_index_html(client: TestClient) -> None:
    """mount('/', StaticFiles(html=True)) → / 요청 시 index.html 자동 매핑."""
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<title>13F Terminal</title>" in r.text


def test_api_routes_take_priority_over_catch_all(client: TestClient) -> None:
    """/api/health 가 StaticFiles 마운트에 가려지지 않는지 확인."""
    r = client.get("/api/health")
    assert r.status_code == 200
    # JSON content (not HTML)
    assert "application/json" in r.headers["content-type"]

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


def test_ask_returns_503_until_chunk_d(client: TestClient) -> None:
    r = client.post(
        "/api/ask",
        json={"question": "test", "period": "2026-03-31"},
    )
    assert r.status_code == 503


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

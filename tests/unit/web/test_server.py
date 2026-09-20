"""Unit tests for web/server.py — verify routes + mount order via TestClient."""
from __future__ import annotations

import re

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


def test_static_assets_require_revalidation(client: TestClient) -> None:
    """Cache-Control이 없으면 브라우저가 Last-Modified로 캐시 수명을 추정해, 수정한 .jsx·.css 대신
    캐시된 예전 파일을 새로고침 후에도 계속 쓴다 (Babel이 XHR로 받는 .jsx 포함)."""
    for path in ("/", "/hf-backtest.jsx", "/hf-styles.css"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.headers.get("cache-control") == "no-cache", path


def test_index_html_versions_local_asset_urls(client: TestClient) -> None:
    """로컬 스크립트·CSS 주소에 파일 수정 시각 기반 버전을 붙여, 이전에 no-cache 없이 캐시된
    사본을 쓰는 브라우저(예: 폰)도 새로고침만으로 새 파일을 받게 한다."""
    r = client.get("/")
    assert r.status_code == 200
    body = r.text
    for asset in ("hf-app.jsx", "hf-components.jsx", "hf-plan.jsx", "hf-styles.css", "hf-data.js"):
        assert re.search(rf'"{asset}\?v=[0-9a-f]+"', body), f"{asset} lacks ?v=: {body[:400]}"
    # CDN·외부 주소는 그대로 둔다 (integrity 해시가 깨지지 않게)
    assert 'unpkg.com/react@18.3.1/umd/react.development.js"' in body
    assert "cdn.jsdelivr.net" in body and "jsdelivr.net/gh/orioncactus/pretendard@v1.3.9" in body


def test_index_html_version_changes_when_an_asset_changes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """파일이 바뀌면 버전도 바뀌어야 캐시가 무시된다."""
    from thirteen_f.web import server

    before = re.search(r'hf-app\.jsx\?v=([0-9a-f]+)', client.get("/").text).group(1)
    stamp = tmp_path / "hf-app.jsx"
    stamp.write_text("// changed", encoding="utf-8")
    monkeypatch.setattr(server, "asset_version", lambda: "deadbeef")
    after = re.search(r'hf-app\.jsx\?v=([0-9a-f]+)', client.get("/").text).group(1)
    assert after == "deadbeef" and after != before


def test_index_html_is_revalidated_not_cached(client: TestClient) -> None:
    r = client.get("/")
    assert r.headers.get("cache-control") == "no-cache"
    assert "text/html" in r.headers["content-type"]


def test_data_mount_also_requires_revalidation() -> None:
    """export JSON(/data)도 같은 규칙 — export로 갱신한 데이터가 캐시에 가려지지 않게."""
    from thirteen_f.web.server import NoCacheStaticFiles, app

    mounts = {r.name: r.app for r in app.routes if getattr(r, "name", None) in ("data", "static")}
    assert set(mounts) == {"data", "static"}
    assert all(isinstance(m, NoCacheStaticFiles) for m in mounts.values())

"""Smoke test for `thirteen-f serve` — subprocess boot + /api/health=200.

Skipped if uv is unavailable. The test polls the health endpoint instead of a
fixed sleep so it survives slow startup; max wait ~10s.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time

import httpx
import pytest


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv CLI not on PATH — required for subprocess invocation",
)
def test_serve_starts_and_health_returns_200(tmp_path) -> None:
    port = _free_port()
    env = os.environ.copy()
    env["SEC_USER_AGENT"] = "test agent"
    env["DUCKDB_PATH"] = str(tmp_path / "smoke.duckdb")

    proc = subprocess.Popen(
        ["uv", "run", "thirteen-f", "serve", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        deadline = time.time() + 20.0
        last_err: Exception | None = None
        while time.time() < deadline:
            if proc.poll() is not None:
                out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
                err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                pytest.fail(f"server exited early (code={proc.returncode})\nSTDOUT:\n{out}\nSTDERR:\n{err}")
            try:
                r = httpx.get(url, timeout=1.5)
                if r.status_code == 200:
                    assert "llm_available" in r.json()
                    return
            except httpx.RequestError as e:
                last_err = e
            time.sleep(0.5)
        pytest.fail(f"timed out waiting for {url} (last error: {last_err})")
    finally:
        # Windows: send CTRL_BREAK_EVENT is unreliable from a non-console child;
        # plain terminate()/kill() is the portable cleanup.
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

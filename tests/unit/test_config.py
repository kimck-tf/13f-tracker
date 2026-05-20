from pathlib import Path

import pytest

from thirteen_f.core.config import Settings, load_settings


def test_settings_loads_user_agent(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('SEC_USER_AGENT="Test User test@example.com"\n')
    monkeypatch.chdir(tmp_path)
    settings = load_settings()
    assert settings.sec_user_agent == "Test User test@example.com"


def test_settings_raises_without_user_agent(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("")  # 비어있음
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        load_settings()


def test_settings_duckdb_path_default(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text('SEC_USER_AGENT="Test User test@example.com"\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    settings = load_settings()
    assert settings.duckdb_path == Path("data/13f.duckdb")

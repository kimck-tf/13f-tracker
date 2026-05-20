from unittest.mock import MagicMock, patch

import pytest

from thirteen_f.collect.edgar_client import EdgarClient


def test_user_agent_required():
    with pytest.raises(ValueError, match="User-Agent"):
        EdgarClient(user_agent="")


def test_get_submissions_url(monkeypatch):
    client = EdgarClient(user_agent="Test User test@example.com")
    mock_resp = MagicMock(status_code=200, json=lambda: {"cik": "1067983"})
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp) as mget:
        result = client.get_submissions("1067983")
    mget.assert_called_once()
    called_url = mget.call_args[0][0]
    assert called_url == "https://data.sec.gov/submissions/CIK0001067983.json"
    assert result == {"cik": "1067983"}


def test_get_submissions_pads_cik(monkeypatch):
    client = EdgarClient(user_agent="Test User test@example.com")
    mock_resp = MagicMock(status_code=200, json=lambda: {})
    mock_resp.raise_for_status = MagicMock()
    with patch.object(client._client, "get", return_value=mock_resp) as mget:
        client.get_submissions("1067983")  # 10자리 미달
    assert "CIK0001067983" in mget.call_args[0][0]

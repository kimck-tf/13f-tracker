from unittest.mock import MagicMock, patch

from thirteen_f.llm.gemini import generate


def test_no_api_key_returns_none():
    assert generate("hi", api_key="") is None
    assert generate("hi", api_key=None) is None  # type: ignore[arg-type]


def test_success_returns_text():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "안녕하세요"}]}
        }]
    }
    with patch("httpx.post", return_value=mock_resp):
        out = generate("test", api_key="fake-key")
    assert out == "안녕하세요"


def test_non_200_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "bad request"
    with patch("httpx.post", return_value=mock_resp):
        assert generate("test", api_key="fake-key") is None


def test_empty_candidates_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"candidates": []}
    with patch("httpx.post", return_value=mock_resp):
        assert generate("test", api_key="fake-key") is None


def test_exception_returns_none():
    with patch("httpx.post", side_effect=Exception("network")):
        assert generate("test", api_key="fake-key") is None


def test_concatenates_multiple_parts():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {"parts": [
                {"text": "Hello "},
                {"text": "world"},
            ]}
        }]
    }
    with patch("httpx.post", return_value=mock_resp):
        assert generate("test", api_key="fake-key") == "Hello world"


def test_thinking_on_does_not_set_budget():
    """enable_thinking=True (기본) → 페이로드에 thinkingConfig 미포함."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
    }
    with patch("httpx.post", return_value=mock_resp) as m:
        generate("test", api_key="k", enable_thinking=True)
        kwargs = m.call_args.kwargs
        gen_cfg = kwargs["json"]["generationConfig"]
        assert "thinkingConfig" not in gen_cfg


def test_thinking_off_sets_budget_zero():
    """enable_thinking=False → thinkingConfig.thinkingBudget=0 으로 thinking 비활성화."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "ok"}]}}]
    }
    with patch("httpx.post", return_value=mock_resp) as m:
        generate("test", api_key="k", enable_thinking=False)
        kwargs = m.call_args.kwargs
        gen_cfg = kwargs["json"]["generationConfig"]
        assert gen_cfg.get("thinkingConfig") == {"thinkingBudget": 0}

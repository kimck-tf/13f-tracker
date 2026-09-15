from unittest.mock import MagicMock

import pytest
import yaml

from thirteen_f.collect.resolve_cik import resolve_cik_by_name, resolve_missing_ciks


def test_resolve_exact_match():
    company_tickers = {
        "0": {"cik_str": 1067983, "ticker": "BRK-A", "title": "BERKSHIRE HATHAWAY INC"},
        "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }
    cik = resolve_cik_by_name("Berkshire Hathaway", company_tickers)
    assert cik == "0001067983"


def test_resolve_no_match_returns_none():
    company_tickers = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    }
    assert resolve_cik_by_name("Some Unknown Co", company_tickers) is None


def test_resolve_case_insensitive_substring():
    company_tickers = {
        "0": {"cik_str": 1336528, "ticker": None, "title": "PERSHING SQUARE CAPITAL MANAGEMENT L.P."},
    }
    cik = resolve_cik_by_name("Pershing Square", company_tickers)
    assert cik == "0001336528"


def test_resolve_missing_ciks_rejects_unquoted_octal_cik(tmp_path):
    """따옴표 없는 0~7 숫자 CIK는 YAML이 8진수 int로 읽는다 → yaml을 덮어쓰기 전에 중단."""
    path = tmp_path / "managers.yaml"
    original = "- name: A\n  label: A\n  cik: 0001061165\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="따옴표"):
        resolve_missing_ciks(path, {})
    assert path.read_text(encoding="utf-8") == original


def test_resolve_missing_ciks_rejects_unquoted_extra_cik(tmp_path):
    """extra_ciks도 같은 8진수 함정이 있다 (예: 0002026053)."""
    path = tmp_path / "managers.yaml"
    original = "- name: A\n  label: A\n  cik: '0001336528'\n  extra_ciks: [0002026053]\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="따옴표"):
        resolve_missing_ciks(path, {})
    assert path.read_text(encoding="utf-8") == original


def test_resolve_missing_ciks_keeps_quoted_cik(tmp_path):
    path = tmp_path / "managers.yaml"
    path.write_text("- name: A\n  label: A\n  cik: '0001061165'\n", encoding="utf-8")

    assert resolve_missing_ciks(path, {}) == 0
    assert yaml.safe_load(path.read_text(encoding="utf-8"))[0]["cik"] == "0001061165"

from unittest.mock import MagicMock

import pytest

from thirteen_f.collect.resolve_cik import resolve_cik_by_name


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

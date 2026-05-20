import pytest

from thirteen_f.collect.price_loader import to_stooq_ticker


def test_to_stooq_ticker_simple():
    assert to_stooq_ticker("AAPL") == "AAPL.US"


def test_to_stooq_ticker_class_share():
    # Spec §5.6: 클래스주 '.' → '-' + '.US'
    assert to_stooq_ticker("BRK.B") == "BRK-B.US"
    assert to_stooq_ticker("BF.B") == "BF-B.US"

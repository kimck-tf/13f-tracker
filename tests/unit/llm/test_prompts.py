from thirteen_f.llm.prompts import (
    quarterly_headline_prompt,
    signal_explain_prompt,
)


def test_headline_prompt_includes_period_and_top_tickers():
    p = quarterly_headline_prompt(
        period="2026-03-31",
        n_managers=15,
        n_holdings=10867,
        top_tickers=[("AAPL", 0.85), ("MSFT", 0.7)],
        change_counts={"new": 100, "increase": 200},
        new_buy_top=[("NVDA", 3, 5)],
    )
    assert "2026-03-31" in p
    assert "AAPL" in p
    assert "MSFT" in p
    assert "10,867" in p
    assert "한국어" in p
    # 면책 문구
    assert "13F 한계" in p
    assert "투자 권유 아님" in p


def test_headline_prompt_handles_empty_changes():
    p = quarterly_headline_prompt(
        period="2024-03-31",
        n_managers=15,
        n_holdings=0,
        top_tickers=[],
        change_counts={},
        new_buy_top=[],
    )
    assert "2024-03-31" in p
    # 비어 있을 때도 prompt가 생성됨
    assert "13F 한계" in p


def test_signal_explain_prompt_per_ticker_line():
    rows = [
        {
            "ticker": "AAPL", "total_score": 0.85,
            "consensus_score": 0.9, "conviction_score": 0.8,
            "continuity_score": 0.7, "cloning_quality_score": 1.0,
            "holder_count": 7, "new_buy_count": 1,
        },
        {
            "ticker": "MSFT", "total_score": 0.7,
            "consensus_score": 0.8, "conviction_score": None,
            "continuity_score": 0.5, "cloning_quality_score": 0.9,
            "holder_count": 5, "new_buy_count": 0,
        },
    ]
    p = signal_explain_prompt(period="2026-03-31", rows=rows)
    assert "AAPL" in p
    assert "MSFT" in p
    # None conviction이 0으로 안전하게 표시
    assert "conviction=0.000" in p
    assert "한국어" in p
    assert "매수 매도 권고 금지" in p

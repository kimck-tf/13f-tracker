"""Gemini 호출 Before/After 비교 — 2026 Q1 데이터.

Before: thinkingBudget=0, max_output_tokens=1024 (headline) / 2048 (explain)
After:  thinking 활성화, max_output_tokens=4096 (headline) / 8192 (explain)
"""
from __future__ import annotations

import time
from datetime import date

import duckdb
import httpx

from thirteen_f.core.config import load_settings
from thirteen_f.llm.prompts import quarterly_headline_prompt, signal_explain_prompt
from thirteen_f.llm.summary import fetch_quarter_context, fetch_top_signals


def call(prompt: str, api_key: str, model: str, max_tok: int, disable_thinking: bool):
    """1회 generateContent 호출, finishReason + usage + text 반환."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    gen_cfg = {"temperature": 0.2, "maxOutputTokens": max_tok}
    if disable_thinking:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
    t0 = time.perf_counter()
    resp = httpx.post(
        url, params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_cfg},
        timeout=180.0,
    )
    elapsed = time.perf_counter() - t0
    data = resp.json()
    cand = (data.get("candidates") or [{}])[0]
    finish = cand.get("finishReason")
    parts = cand.get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
    usage = data.get("usageMetadata", {})
    return {
        "finishReason": finish,
        "promptTokens": usage.get("promptTokenCount"),
        "thoughtsTokens": usage.get("thoughtsTokenCount", 0),
        "candidatesTokens": usage.get("candidatesTokenCount", 0),
        "totalTokens": usage.get("totalTokenCount"),
        "text": text,
        "elapsed_s": round(elapsed, 2),
    }


def fmt_row(label: str, r: dict) -> str:
    return (
        f"  {label:<8} | finish={r['finishReason']:<10} | "
        f"prompt={r['promptTokens']:>4} thoughts={r['thoughtsTokens']:>5} "
        f"resp={r['candidatesTokens']:>4} total={r['totalTokens']:>5} | "
        f"{r['elapsed_s']:>5.2f}s | resp_len={len(r['text'])}"
    )


def main():
    settings = load_settings()
    if not settings.google_api_key:
        print("ERROR: GOOGLE_API_KEY 미설정")
        return
    model = settings.google_model
    period = date(2026, 3, 31)
    conn = duckdb.connect("data/13f.duckdb", read_only=True)

    # Prompt 1: HEADLINE
    ctx = fetch_quarter_context(conn, period)
    hp = quarterly_headline_prompt(
        ctx["period"], ctx["n_managers"], ctx["n_holdings"],
        ctx["top_tickers"], ctx["change_counts"], ctx["new_buy_top"],
    )
    # Prompt 2: EXPLAIN top 10
    rows = fetch_top_signals(conn, period, top_n=10)
    ep = signal_explain_prompt(str(period), rows)

    print(f"=== Gemini Before/After 비교 ===")
    print(f"Model: {model}")
    print(f"Period: {period}")
    print()

    # --- HEADLINE ---
    print("[1] HEADLINE SUMMARY")
    before_h = call(hp, settings.google_api_key, model, max_tok=1024, disable_thinking=True)
    after_h = call(hp, settings.google_api_key, model, max_tok=4096, disable_thinking=False)
    print(fmt_row("Before", before_h))
    print(fmt_row("After", after_h))
    print()
    print("  --- Before text ---")
    print("  " + (before_h["text"].replace("\n", "\n  ") if before_h["text"] else "(empty)"))
    print()
    print("  --- After text ---")
    print("  " + (after_h["text"].replace("\n", "\n  ") if after_h["text"] else "(empty)"))
    print()

    # --- EXPLAIN ---
    print("[2] TOP 10 SIGNAL EXPLAIN")
    before_e = call(ep, settings.google_api_key, model, max_tok=2048, disable_thinking=True)
    after_e = call(ep, settings.google_api_key, model, max_tok=8192, disable_thinking=False)
    print(fmt_row("Before", before_e))
    print(fmt_row("After", after_e))
    print()
    print("  --- Before text ---")
    print("  " + (before_e["text"].replace("\n", "\n  ") if before_e["text"] else "(empty)"))
    print()
    print("  --- After text ---")
    print("  " + (after_e["text"].replace("\n", "\n  ") if after_e["text"] else "(empty)"))


if __name__ == "__main__":
    main()

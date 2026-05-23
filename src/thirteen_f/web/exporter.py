"""DuckDB → JSON dumper for static SPA (Phase 5).

Each export_* function writes one or more JSON files to ``out_dir``. The JSON
schema is defined in :mod:`thirteen_f.web.schemas` (SSOT).
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb

from thirteen_f.core.dates import quarter_label

from .schemas import Manager, Meta, QuarterEntry


def _avatar_from_name(name: str) -> str:
    """'Warren Buffett' -> 'WB'."""
    return "".join(w[0] for w in name.split() if w)[:2].upper()


def export_managers(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``managers.json`` — list of Manager records.

    id = label (lowercased), avatar derived from full name initials.
    """
    rows = conn.execute(
        """
        SELECT label, name, fund, style, color, notes
        FROM managers
        ORDER BY label
        """
    ).fetchall()
    payload = []
    for label, name, fund, style, color, notes in rows:
        if not label:
            continue
        payload.append(
            Manager(
                id=label.lower(),
                name=name,
                firm=fund or "",
                style=style or "",
                color=color or "#1d6dc8",
                avatar=_avatar_from_name(name),
                note=notes or "",
            ).model_dump()
        )
    (out_dir / "managers.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_quarters(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``quarters.json`` (ordered list) and ``quarters_index.json`` (date→idx)."""
    rows = conn.execute(
        """
        SELECT DISTINCT period_of_report
        FROM filings
        WHERE period_of_report IS NOT NULL
        ORDER BY period_of_report
        """
    ).fetchall()
    payload: list[dict] = []
    idx_map: dict[str, int] = {}
    for i, (period,) in enumerate(rows):
        q = (period.month - 1) // 3 + 1
        year_short = f"{period.year % 100:02d}"
        key = f"{period.year}Q{q}"
        label = f"Q{q}'{year_short}"
        iso = period.isoformat()
        payload.append(
            QuarterEntry(key=key, label=label, date=iso).model_dump()
        )
        idx_map[iso] = i
    (out_dir / "quarters.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "quarters_index.json").write_text(
        json.dumps(idx_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_meta(
    conn: duckdb.DuckDBPyConnection,
    out_dir: Path,
    llm_available: bool,
) -> None:
    """Export ``meta.json`` — single Meta record summarising the dump."""
    mgr_count = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0]
    stock_count = conn.execute(
        "SELECT COUNT(DISTINCT ticker) FROM cusip_ticker_map WHERE ticker IS NOT NULL"
    ).fetchone()[0]
    latest = conn.execute(
        "SELECT MAX(period_of_report) FROM filings"
    ).fetchone()[0]
    now = datetime.now(UTC)
    meta = Meta(
        generated_at=now,
        latest_period=latest.isoformat() if latest else "",
        data_version=str(int(now.timestamp())),
        mgr_count=mgr_count,
        stock_count=stock_count,
        llm_available=llm_available,
    )
    (out_dir / "meta.json").write_text(
        meta.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _quarter_end_dates(conn: duckdb.DuckDBPyConnection) -> list:
    rows = conn.execute(
        """
        SELECT DISTINCT period_of_report FROM filings
        WHERE period_of_report IS NOT NULL ORDER BY period_of_report
        """
    ).fetchall()
    return [r[0] for r in rows]


def export_stocks(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``stocks.json`` — per-ticker name/sector/industry + quarter-end close series.

    Source: ``cusip_ticker_map`` (sector/industry must be backfilled via
    ``scripts/supplement_sector.py``); falls back to "Other" if missing.

    I3: SQL 호출 횟수를 N_ticker × N_quarter → N_quarter로 줄임 (예: 1584 × 9 → 9).
    각 분기에 대해 한 번에 모든 ticker의 분기말 close를 가져오고, 결과를 ticker별
    px 배열로 조립.
    """
    q_dates = _quarter_end_dates(conn)
    rows = conn.execute(
        """
        SELECT ticker,
               COALESCE(NULLIF(name, ''), ticker)    AS display_name,
               COALESCE(NULLIF(sector, ''), 'Other') AS sector,
               COALESCE(industry, '')                AS industry
        FROM cusip_ticker_map
        WHERE ticker IS NOT NULL
        ORDER BY ticker
        """
    ).fetchall()
    tickers = [r[0] for r in rows]
    # 분기별 한 번에 모든 ticker의 분기말 close 조회 (DuckDB MAX_BY)
    px_matrix: dict[str, list[float | None]] = {t: [None] * len(q_dates) for t in tickers}
    for q_idx, qd in enumerate(q_dates):
        for ticker, close in conn.execute(
            """
            SELECT ticker, MAX_BY(close, date) AS close_at_qend
            FROM prices
            WHERE date <= ?
            GROUP BY ticker
            """,
            (qd,),
        ).fetchall():
            if ticker in px_matrix and close is not None:
                px_matrix[ticker][q_idx] = float(close)
    payload: list[dict] = []
    for ticker, display_name, sector, industry in rows:
        payload.append({
            "t": ticker,
            "n": display_name,
            "s": sector,
            "i": industry or None,
            "px": px_matrix[ticker],
        })
    (out_dir / "stocks.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_prices_split(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``prices/{TICKER}.json`` — one file per ticker, daily close series.

    Lazy-loaded by the SPA only when a stock detail page is opened.
    """
    prices_dir = out_dir / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    tickers = conn.execute(
        "SELECT DISTINCT ticker FROM prices WHERE ticker IS NOT NULL ORDER BY ticker"
    ).fetchall()
    for (ticker,) in tickers:
        rows = conn.execute(
            "SELECT date, close FROM prices WHERE ticker = ? ORDER BY date",
            (ticker,),
        ).fetchall()
        payload = {
            "date": [r[0].isoformat() for r in rows],
            "close": [float(r[1]) if r[1] is not None else None for r in rows],
        }
        (prices_dir / f"{ticker}.json").write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )


def export_holdings(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``holdings.json`` and ``holdings_unmapped.json``.

    Shape: ``{manager_label: {ticker: [shares_per_quarter_in_millions]}}``.
    Unmapped CUSIPs (no ticker in cusip_ticker_map) are isolated into the
    second file so the SPA can ignore them safely while preserving raw data.

    Note on ``filed_at <= q + 180 days`` filter:
      - SPA는 시계열 viewer라 분기말 filing은 모두 표시하는 게 의도.
      - ``period_of_report = q`` 자체 조건만으로 미래 분기 filing은 제외되어 lookahead 위험 없음.
      - 180일 cutoff는 SEC 룰(45일)을 6개월 cushion으로 늘려 ``delinquent late filing``만
        제외하기 위함. ``superseded_by IS NULL``로 정정본 중 최신만 선택되므로,
        180일 이내 도착한 정정본은 모두 잡힘. 180일 이후 도착하는 case는 사실상 0건.
    """
    quarters = _quarter_end_dates(conn)
    q_count = len(quarters)
    managers = conn.execute("SELECT cik, label FROM managers ORDER BY label").fetchall()
    payload: dict[str, dict[str, list[float]]] = {}
    unmapped: dict[str, dict[str, dict]] = {}

    for cik, label in managers:
        if not label:
            continue
        mgr_id = label.lower()
        by_ticker: dict[str, list[float]] = {}
        unmapped_rows: dict[str, dict] = {}
        for i, q in enumerate(quarters):
            cutoff = q + timedelta(days=180)
            rows = conn.execute(
                """
                SELECT h.cusip, m.ticker, h.name_of_issuer, SUM(h.shares) AS shares
                FROM holdings h
                JOIN filings f ON f.accession_no = h.accession_no
                LEFT JOIN cusip_ticker_map m ON m.cusip = h.cusip
                WHERE f.cik = ? AND f.period_of_report = ?
                  AND f.filed_at <= ? AND f.superseded_by IS NULL
                GROUP BY h.cusip, m.ticker, h.name_of_issuer
                """,
                (cik, q, cutoff),
            ).fetchall()
            for cusip, ticker, name, shares in rows:
                shares_m = float(shares or 0) / 1e6  # 백만주 단위
                if ticker:
                    by_ticker.setdefault(ticker, [0.0] * q_count)[i] = shares_m
                else:
                    entry = unmapped_rows.setdefault(
                        cusip,
                        {"name_of_issuer": name or "", "shares": [0.0] * q_count},
                    )
                    entry["shares"][i] = shares_m
        payload[mgr_id] = by_ticker
        if unmapped_rows:
            unmapped[mgr_id] = unmapped_rows

    (out_dir / "holdings.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "holdings_unmapped.json").write_text(
        json.dumps(unmapped, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resample_quarterly(
    curves: list[tuple[date, float, float, int]],
) -> tuple[list[float], list[float], list[float], list[float]]:
    """daily curves [(date, nav, bench_nav, pos_cnt)] → 분기말 equity/drawdown/qrets/bench.

    Quarter-end은 같은 분기 라벨의 마지막 영업일 (덮어쓰기로 보존).
    """
    by_q: dict[str, tuple[date, float, float]] = {}
    for d, nav, bench, _ in curves:
        q_lab = quarter_label(d)
        by_q[q_lab] = (d, float(nav), float(bench))
    sorted_q = sorted(by_q.keys())
    equity = [by_q[q][1] for q in sorted_q]
    bench = [by_q[q][2] for q in sorted_q]
    # drawdown: 누적 최고 대비 하락률
    peak = 0.0
    dd: list[float] = []
    for v in equity:
        peak = max(peak, v)
        dd.append((v - peak) / peak if peak > 0 else 0.0)
    # quarterly return
    qrets: list[float] = [0.0]
    for j in range(1, len(equity)):
        prev = equity[j - 1]
        qrets.append((equity[j] / prev - 1.0) if prev > 0 else 0.0)
    return equity, dd, qrets, bench


def _group_holdings_by_date(rows: list[tuple[date, str, float]]) -> list[dict]:
    """[(rebalance_date, ticker, weight)] → [{date, holdings:[{ticker, weight}, ...]}]."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for d, ticker, weight in rows:
        grouped[d.isoformat()].append({"ticker": ticker, "weight": float(weight)})
    return [{"date": k, "holdings": v} for k, v in sorted(grouped.items())]


def export_backtest(conn: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    """Export ``backtest.json`` — list of run records with equity/dd/qrets/holdingsLog/metrics."""
    runs = conn.execute(
        """
        SELECT r.run_id, r.strategy_name, r.params_json, r.start_date, r.end_date,
               m.total_return, m.cagr, m.sharpe, m.sortino, m.mdd, m.calmar,
               m.win_rate_quarterly, m.bench_total_return, m.bench_cagr
        FROM backtest_runs r
        LEFT JOIN backtest_metrics m ON m.run_id = r.run_id
        ORDER BY r.created_at DESC
        """
    ).fetchall()

    payload: list[dict] = []
    for (
        run_id, name, params_json, _sd, _ed,
        total_ret, m_cagr, m_sharpe, m_sortino, m_mdd, m_calmar,
        m_winq, m_bench_total, m_bench_cagr,
    ) in runs:
        curves = conn.execute(
            """
            SELECT date, nav, benchmark_nav, position_count FROM backtest_curves
            WHERE run_id = ? ORDER BY date
            """,
            (run_id,),
        ).fetchall()
        equity, dd, qrets, bench = _resample_quarterly(curves)

        holdings_log = conn.execute(
            """
            SELECT rebalance_date, ticker, weight FROM backtest_holdings
            WHERE run_id = ? ORDER BY rebalance_date, weight DESC
            """,
            (run_id,),
        ).fetchall()
        holdings_grouped = _group_holdings_by_date(holdings_log)

        payload.append({
            "run_id": run_id,
            "name": name,
            "params": json.loads(params_json) if params_json else {},
            "equity": equity,
            "dd": dd,
            "qrets": qrets,
            "benchEquity": bench,
            "holdingsLog": holdings_grouped,
            "metrics": {
                "totalRet": total_ret,
                "cagr": m_cagr,
                "sharpe": m_sharpe,
                "sortino": m_sortino,
                "maxDD": m_mdd,
                "calmar": m_calmar,
                "hitRate": m_winq,
                "benchTotalRet": m_bench_total,
                "benchCagr": m_bench_cagr,
            },
        })
    (out_dir / "backtest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

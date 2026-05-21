"""홈 — 최신 분기 헤드라인 + 거장 활동 요약."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard._theme import apply_theme, kpi_card, section, sidebar_toggle, status_bar
from thirteen_f.dashboard.tables import (
    get_read_only_conn,
    latest_period,
    manager_list,
    top_scores,
)

st.set_page_config(
    page_title="13F · Quiet Finance Terminal",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
sidebar_toggle()

st.title("13F Portfolio Tracker")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))


@st.cache_data(ttl=600)
def _top_signals(period_iso: str):
    from datetime import date
    p = date.fromisoformat(period_iso)
    return top_scores(conn, p, top_n=10)


@st.cache_data(ttl=600)
def _managers():
    return manager_list(conn)


@st.cache_data(ttl=600)
def _summary_stats(period_iso: str):
    from datetime import date
    p = date.fromisoformat(period_iso)
    n_managers = conn.execute(
        "SELECT COUNT(DISTINCT cik) FROM filings WHERE period_of_report = ? AND superseded_by IS NULL",
        (p,),
    ).fetchone()[0]
    n_holdings = conn.execute(
        "SELECT COUNT(*) FROM holdings h JOIN filings f ON h.accession_no=f.accession_no "
        "WHERE f.period_of_report = ? AND f.superseded_by IS NULL",
        (p,),
    ).fetchone()[0]
    changes = conn.execute(
        "SELECT change_type, COUNT(*) FROM signals_quarterly WHERE period_of_report=? GROUP BY 1",
        (p,),
    ).fetchall()
    cd = {k: v for k, v in changes}
    return n_managers, n_holdings, cd


period = latest_period(conn)

if not period:
    st.info("아직 데이터가 없습니다. `thirteen-f collect → analyze`를 먼저 실행하세요.")
    st.stop()

n_managers, n_holdings, change_dict = _summary_stats(period.isoformat())

# === Status bar — 페이지 상단 metadata ===
status_bar([
    ("PERIOD", str(period), "amber"),
    ("MANAGERS", f"{n_managers}", "muted"),
    ("HOLDINGS", f"{n_holdings:,}", "muted"),
    ("NEW BUYS", f"{change_dict.get('new', 0)}", "green"),
    ("INCREASES", f"{change_dict.get('increase', 0)}", "green"),
    ("DECREASES", f"{change_dict.get('decrease', 0)}", "red"),
    ("HOLDS", f"{change_dict.get('hold', 0)}", "muted"),
])

st.caption(
    "본 도구의 시그널은 13F 데이터의 구조적 한계 — 45일 지연·롱 온리·분기 스냅샷·기밀 처리 — 를 전제로 합니다. 모든 결과는 참고용."
)

# === KPI band — 4 metrics ===
section("Quarter Snapshot")
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Period", str(period))
with c2:
    kpi_card("Reporting Managers", f"{n_managers}", delta=f"of 15 tracked", delta_color="neutral")
with c3:
    total_changes = sum(change_dict.values())
    new_pct = (change_dict.get('new', 0) / total_changes * 100) if total_changes else 0
    kpi_card("Total Position Changes", f"{total_changes:,}",
             delta=f"{change_dict.get('new', 0)} new · {new_pct:.1f}%", delta_color="green")
with c4:
    net_flow = change_dict.get('increase', 0) + change_dict.get('new', 0) - change_dict.get('decrease', 0) - change_dict.get('exit', 0)
    kpi_card("Net Flow",
             f"{net_flow:+,}",
             delta="incr+new − decr−exit",
             delta_color="green" if net_flow > 0 else "red")

st.markdown("")  # spacing

# === Two-column body ===
col_left, col_right = st.columns([1, 1], gap="large")

with col_left:
    section("Tracked Managers")
    mgr_df = _managers()
    st.dataframe(
        mgr_df.drop(columns=["cik"], errors="ignore"),
        use_container_width=True, hide_index=True,
        column_config={
            "label": st.column_config.TextColumn("Label", width="small"),
            "name": st.column_config.TextColumn("Name", width="medium"),
            "fund": st.column_config.TextColumn("Fund", width="medium"),
            "style": st.column_config.TextColumn("Style", width="small"),
            "active_since": st.column_config.NumberColumn("Since", format="%d", width="small"),
            "cloning_score_weight": st.column_config.ProgressColumn(
                "Cloning Wt", min_value=0.0, max_value=1.0, format="%.2f", width="small",
            ),
        },
        height=560,
    )

with col_right:
    section("Top 10 by Composite Score")
    top10 = _top_signals(period.isoformat())
    st.dataframe(
        top10,
        use_container_width=True, hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("TICKER", width="small"),
            "cusip": st.column_config.TextColumn("CUSIP", width="small"),
            "total_score": st.column_config.ProgressColumn(
                "Score", min_value=0.0, max_value=1.0, format="%.3f"),
            "consensus_score": st.column_config.NumberColumn("Cons", format="%.2f", width="small"),
            "conviction_score": st.column_config.NumberColumn("Conv", format="%.2f", width="small"),
            "continuity_score": st.column_config.NumberColumn("Cont", format="%.2f", width="small"),
            "cloning_quality_score": st.column_config.NumberColumn("Qual", format="%.2f", width="small"),
        },
        height=560,
    )

st.caption(
    "Composite Score = 0.30·consensus + 0.30·conviction + 0.20·continuity + 0.20·cloning_quality (Spec §6.1)"
)

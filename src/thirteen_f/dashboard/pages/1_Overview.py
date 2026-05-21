"""Page 1: 분기 개요 — Consensus heatmap + Change waterfall + New buys."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard._theme import apply_theme, section, sidebar_toggle, status_bar
from thirteen_f.dashboard.charts import change_waterfall, consensus_heatmap
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Overview · 13F", page_icon="◆", layout="wide")
apply_theme()
sidebar_toggle()

st.title("Quarter Overview")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM consensus_quarterly ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()

if not quarters:
    st.info("분석 결과가 없습니다. `thirteen-f analyze`를 먼저 실행하세요.")
    st.stop()

st.sidebar.markdown("### Quarter")
selected = st.sidebar.selectbox("분기 선택", quarters, index=0, label_visibility="collapsed")


@st.cache_data(ttl=600)
def _consensus_matrix(period_iso: str) -> pd.DataFrame:
    from datetime import date
    p = date.fromisoformat(period_iso)
    rows = conn.execute(
        """
        SELECT s.cusip, COALESCE(m.ticker, s.cusip) AS ticker,
               mn.label, s.weight_pct
        FROM signals_quarterly s
        JOIN managers mn ON mn.cik = s.cik
        LEFT JOIN cusip_ticker_map m ON m.cusip = s.cusip
        WHERE s.period_of_report = ? AND s.change_type != 'exit'
        """,
        (p,),
    ).fetchdf()
    if rows.empty:
        return pd.DataFrame()
    matrix = rows.pivot_table(
        index="ticker", columns="label", values="weight_pct", fill_value=0
    )
    matrix["__sum"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("__sum", ascending=False).head(30).drop(columns="__sum")
    return matrix


@st.cache_data(ttl=600)
def _change_counts(period_iso: str) -> dict[str, int]:
    from datetime import date
    p = date.fromisoformat(period_iso)
    rows = conn.execute(
        "SELECT change_type, COUNT(*) FROM signals_quarterly WHERE period_of_report = ? GROUP BY 1",
        (p,),
    ).fetchall()
    return {r[0]: r[1] for r in rows}


@st.cache_data(ttl=600)
def _new_buys(period_iso: str) -> pd.DataFrame:
    from datetime import date
    p = date.fromisoformat(period_iso)
    return conn.execute(
        """
        SELECT m.ticker, c.cusip, c.new_buy_count, c.holder_count, c.holder_ciks
        FROM consensus_quarterly c
        LEFT JOIN cusip_ticker_map m ON m.cusip = c.cusip
        WHERE c.period_of_report = ? AND c.new_buy_count >= 1
        ORDER BY c.new_buy_count DESC, c.holder_count DESC
        LIMIT 20
        """,
        (p,),
    ).fetchdf()


counts = _change_counts(selected.isoformat())
total = sum(counts.values())

# Status bar
status_bar([
    ("PERIOD", str(selected), "amber"),
    ("TOTAL CHANGES", f"{total:,}", "muted"),
    ("NEW", f"{counts.get('new', 0):,}", "green"),
    ("INCREASE", f"{counts.get('increase', 0):,}", "green"),
    ("HOLD", f"{counts.get('hold', 0):,}", "muted"),
    ("DECREASE", f"{counts.get('decrease', 0):,}", "red"),
    ("EXIT", f"{counts.get('exit', 0):,}", "red"),
])

# Heatmap + waterfall
col1, col2 = st.columns([2, 1], gap="large")
with col1:
    section("Consensus Heatmap · Top 30 by total weight × Manager")
    matrix = _consensus_matrix(selected.isoformat())
    if matrix.empty:
        st.warning("이 분기에 데이터가 없습니다.")
    else:
        fig = consensus_heatmap(matrix)
        fig.update_layout(height=620, title=None, margin=dict(l=80, r=20, t=20, b=60))
        st.plotly_chart(fig, use_container_width=True)

with col2:
    section("Change Type Distribution")
    if counts:
        fig = change_waterfall(counts)
        fig.update_layout(height=300, title=None, margin=dict(l=40, r=20, t=10, b=40))
        st.plotly_chart(fig, use_container_width=True)

# New buys table
section("Top New Buys · Consensus")
nb = _new_buys(selected.isoformat())
if nb.empty:
    st.info("이 분기 신규 매수 컨센서스 종목이 없습니다.")
else:
    st.dataframe(
        nb,
        use_container_width=True, hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("TICKER", width="small"),
            "cusip": st.column_config.TextColumn("CUSIP", width="small"),
            "new_buy_count": st.column_config.NumberColumn("NEW BUYS", format="%d", width="small"),
            "holder_count": st.column_config.NumberColumn("HOLDERS", format="%d", width="small"),
            "holder_ciks": st.column_config.TextColumn("HOLDER CIKs", width="large"),
        },
    )

st.caption(
    "Consensus = 같은 종목을 동시 보유한 거장 수. New Buys = 이번 분기 신규 진입한 거장 수."
)

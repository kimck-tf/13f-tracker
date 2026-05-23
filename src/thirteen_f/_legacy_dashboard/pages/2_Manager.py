"""Page 2: 거장 1명 상세 — 분기 추이 + 트리맵 + 변화 테이블."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from thirteen_f.analyze.concentration import hhi
from thirteen_f.core.config import load_settings
from thirteen_f._legacy_dashboard._theme import apply_theme, kpi_card, section, sidebar_toggle, status_bar
from thirteen_f._legacy_dashboard.charts import portfolio_treemap
from thirteen_f._legacy_dashboard.tables import get_read_only_conn, manager_history

st.set_page_config(page_title="Manager · 13F", page_icon="◆", layout="wide")
apply_theme()
sidebar_toggle()

st.title("Manager Detail")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

managers = conn.execute(
    "SELECT cik, label, name, fund, style FROM managers ORDER BY label"
).fetchdf()
if managers.empty:
    st.info("거장 데이터가 없습니다.")
    st.stop()

st.sidebar.markdown("### Manager")
label_to_cik = dict(zip(managers["label"], managers["cik"]))
selected_label = st.sidebar.selectbox(
    "거장", managers["label"].tolist(), label_visibility="collapsed"
)
cik = label_to_cik[selected_label]
mgr_row = managers[managers["cik"] == cik].iloc[0]


@st.cache_data(ttl=600)
def _history(cik: str) -> pd.DataFrame:
    return manager_history(conn, cik)


hist = _history(cik)
if hist.empty:
    status_bar([
        ("MANAGER", selected_label, "amber"),
        ("STATUS", "NO DATA", "red"),
    ])
    st.warning(f"`{selected_label}` 에 대한 holdings 데이터가 없습니다. (Confidential Treatment 또는 13F-NT 가능)")
    st.stop()

quarters = sorted(hist["period_of_report"].unique(), reverse=True)
st.sidebar.markdown("### Quarter")
sel_q = st.sidebar.selectbox(
    "분기", quarters, label_visibility="collapsed",
    format_func=lambda d: str(d),
)
if hasattr(sel_q, "date") and callable(sel_q.date):
    sel_q = sel_q.date()
sel = hist[hist["period_of_report"] == sel_q]

# 가중치 dict (ticker 누락 시 cusip 사용)
weights = dict(zip(sel["ticker"].fillna(sel["cusip"]), sel["weight_pct"]))
weights = {k: v for k, v in weights.items() if v and v > 0}

# Status bar
status_bar([
    ("MANAGER", selected_label, "amber"),
    ("FUND", str(mgr_row["fund"]), "muted"),
    ("STYLE", str(mgr_row["style"]).upper(), "muted"),
    ("QUARTER", str(sel_q), "amber"),
    ("POSITIONS", f"{len(weights)}", "muted"),
])

# KPI band
hhi_val = hhi(list(weights.values())) if weights else 0.0
top5_weight = sum(sorted(weights.values(), reverse=True)[:5]) if weights else 0.0
top10_weight = sum(sorted(weights.values(), reverse=True)[:10]) if weights else 0.0

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Holdings", f"{len(weights)}")
with c2:
    kpi_card("HHI Concentration", f"{hhi_val:.4f}",
             delta="0=분산 1=집중", delta_color="neutral")
with c3:
    kpi_card("Top 5 Weight", f"{top5_weight*100:.1f}%")
with c4:
    kpi_card("Top 10 Weight", f"{top10_weight*100:.1f}%")

st.markdown("")

# Holdings count over time
col_left, col_right = st.columns([1, 1], gap="large")
with col_left:
    section("Holdings Count over Quarters")
    counts_df = hist.groupby("period_of_report").size().reset_index(name="holdings_n")
    counts_df["period_of_report"] = counts_df["period_of_report"].astype(str)
    st.line_chart(
        counts_df.set_index("period_of_report")["holdings_n"],
        height=320, color="#00C896",
    )

with col_right:
    section(f"Portfolio Treemap · {sel_q}")
    if weights:
        fig = portfolio_treemap(weights)
        fig.update_layout(height=360, margin=dict(l=4, r=4, t=10, b=4), title=None)
        st.plotly_chart(fig, use_container_width=True)

# Recent changes table
section(f"Position Changes @ {sel_q}")
display_df = sel[["ticker", "cusip", "change_type", "weight_pct", "conviction_score", "continuity_score"]].sort_values("weight_pct", ascending=False)
st.dataframe(
    display_df,
    use_container_width=True, hide_index=True,
    column_config={
        "ticker": st.column_config.TextColumn("TICKER", width="small"),
        "cusip": st.column_config.TextColumn("CUSIP", width="small"),
        "change_type": st.column_config.TextColumn("Δ", width="small"),
        "weight_pct": st.column_config.ProgressColumn(
            "Weight", min_value=0.0, max_value=float(display_df["weight_pct"].max() or 1.0),
            format="%.3f"),
        "conviction_score": st.column_config.NumberColumn("Conviction", format="%.3f"),
        "continuity_score": st.column_config.NumberColumn("Continuity", format="%.3f"),
    },
    height=420,
)

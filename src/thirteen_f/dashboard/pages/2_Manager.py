"""Page 2: 거장 1명 상세 — 분기 추이 + 트리맵 + 변화 테이블."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from thirteen_f.analyze.concentration import hhi
from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.charts import portfolio_treemap
from thirteen_f.dashboard.tables import get_read_only_conn, manager_history

st.set_page_config(page_title="Manager", layout="wide")
st.title("Manager Detail")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

managers = conn.execute(
    "SELECT cik, label, name, fund FROM managers ORDER BY label"
).fetchdf()
if managers.empty:
    st.info("거장 데이터가 없습니다.")
    st.stop()

label_to_cik = dict(zip(managers["label"], managers["cik"]))
selected_label = st.sidebar.selectbox("거장 선택", managers["label"].tolist())
cik = label_to_cik[selected_label]

st.markdown(
    f"**{managers[managers['cik']==cik].iloc[0]['name']}** — "
    f"{managers[managers['cik']==cik].iloc[0]['fund']}"
)


@st.cache_data(ttl=600)
def _history(cik: str) -> pd.DataFrame:
    return manager_history(conn, cik)


hist = _history(cik)
if hist.empty:
    st.warning("이 거장에 대한 데이터가 없습니다.")
    st.stop()

# 분기별 보유 종목 수 추이
counts = hist.groupby("period_of_report").size().reset_index(name="holdings_n")
st.subheader("Holdings count over time")
st.line_chart(counts.set_index("period_of_report")["holdings_n"])

# 분기 슬라이더 → 트리맵
quarters = sorted(hist["period_of_report"].unique(), reverse=True)
sel_q = st.sidebar.selectbox("분기", quarters)
sel = hist[hist["period_of_report"] == sel_q]
weights = dict(zip(sel["ticker"].fillna(sel["cusip"]), sel["weight_pct"]))
weights = {k: v for k, v in weights.items() if v and v > 0}

col1, col2 = st.columns([2, 1])
with col1:
    st.subheader(f"Portfolio @ {sel_q}")
    if weights:
        st.plotly_chart(portfolio_treemap(weights), use_container_width=True)
with col2:
    st.subheader("Metrics")
    st.metric("Holdings", len(weights))
    st.metric("HHI", f"{hhi(list(weights.values())):.4f}")
    st.metric("Top 5 weight", f"{sum(sorted(weights.values(), reverse=True)[:5]):.1%}")

st.subheader("Recent Changes")
st.dataframe(
    sel[["ticker", "cusip", "change_type", "weight_pct", "conviction_score", "continuity_score"]]
    .sort_values("weight_pct", ascending=False),
    use_container_width=True, hide_index=True,
)

"""Page 1: 분기 개요 — 컨센서스 매트릭스 + 변화 워터폴."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.charts import change_waterfall, consensus_heatmap
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Overview", layout="wide")
st.title("Quarter Overview")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM consensus_quarterly ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()

if not quarters:
    st.info("분석 결과가 없습니다. `thirteen-f analyze`를 먼저 실행하세요.")
    st.stop()

selected = st.sidebar.selectbox("분기 선택", quarters, index=0)


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
    # 상위 30 종목만 (합계 기준)
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


col1, col2 = st.columns([2, 1])
with col1:
    st.subheader("Consensus Heatmap (Top 30 by total weight)")
    matrix = _consensus_matrix(selected.isoformat())
    if matrix.empty:
        st.warning("이 분기에 데이터가 없습니다.")
    else:
        st.plotly_chart(consensus_heatmap(matrix), use_container_width=True)

with col2:
    st.subheader("Change Type Distribution")
    counts = _change_counts(selected.isoformat())
    if counts:
        st.plotly_chart(change_waterfall(counts), use_container_width=True)

st.subheader("Top New Buys (Consensus)")
nb = _new_buys(selected.isoformat())
st.dataframe(nb, use_container_width=True, hide_index=True)

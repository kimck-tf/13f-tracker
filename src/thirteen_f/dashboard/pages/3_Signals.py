"""Page 3: 종합 점수 랭킹 — 가중치 슬라이더로 실시간 재계산."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard._theme import apply_theme, kpi_card, section, sidebar_toggle, status_bar
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Signals · 13F", page_icon="◆", layout="wide")
apply_theme()
sidebar_toggle()

st.title("Composite Score Ranking")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM total_scores ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()
if not quarters:
    st.info("점수 데이터가 없습니다. `thirteen-f analyze`를 실행하세요.")
    st.stop()

st.sidebar.markdown("### Quarter")
quarter = st.sidebar.selectbox("Quarter", quarters, label_visibility="collapsed")

st.sidebar.markdown("### Weights · 합=1.0")
w_cons = st.sidebar.slider("Consensus", 0.0, 1.0, 0.30, 0.05)
w_conv = st.sidebar.slider("Conviction", 0.0, 1.0, 0.30, 0.05)
w_cont = st.sidebar.slider("Continuity", 0.0, 1.0, 0.20, 0.05)
w_qual = st.sidebar.slider("Cloning Quality", 0.0, 1.0, 0.20, 0.05)
weights_sum = w_cons + w_conv + w_cont + w_qual

st.sidebar.markdown("### Filters")
min_holders = st.sidebar.slider("Min Holders", 1, 15, 1)
top_n = st.sidebar.slider("Top N", 10, 100, 50)

# Status bar
status_bar([
    ("PERIOD", str(quarter), "amber"),
    ("Σ WEIGHTS", f"{weights_sum:.2f}", "green" if abs(weights_sum - 1.0) <= 0.001 else "red"),
    ("MIN HOLDERS", f"{min_holders}", "muted"),
    ("TOP N", f"{top_n}", "muted"),
])

# Weight band
section("Component Weight Composition")
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Consensus", f"{w_cons:.2f}", delta=f"{w_cons/weights_sum*100:.0f}% share" if weights_sum > 0 else "—", delta_color="neutral")
with c2:
    kpi_card("Conviction", f"{w_conv:.2f}", delta=f"{w_conv/weights_sum*100:.0f}% share" if weights_sum > 0 else "—", delta_color="neutral")
with c3:
    kpi_card("Continuity", f"{w_cont:.2f}", delta=f"{w_cont/weights_sum*100:.0f}% share" if weights_sum > 0 else "—", delta_color="neutral")
with c4:
    kpi_card("Cloning Quality", f"{w_qual:.2f}", delta=f"{w_qual/weights_sum*100:.0f}% share" if weights_sum > 0 else "—", delta_color="neutral")

if abs(weights_sum - 1.0) > 0.001:
    st.warning(f"가중치 합 = {weights_sum:.2f} (1.0 권장). 사이드바 슬라이더로 조정하세요.")

# Data + recompute
df = conn.execute(
    """
    SELECT t.ticker, t.cusip,
           t.consensus_score, t.conviction_score, t.continuity_score, t.cloning_quality_score,
           c.holder_count, c.new_buy_count
    FROM total_scores t
    JOIN consensus_quarterly c
      ON t.period_of_report = c.period_of_report AND t.cusip = c.cusip
    WHERE t.period_of_report = ? AND c.holder_count >= ?
    """,
    (quarter, min_holders),
).fetchdf()

if df.empty:
    st.warning("필터에 맞는 데이터가 없습니다.")
    st.stop()

df["recomputed_score"] = (
    df["consensus_score"] * w_cons
    + df["conviction_score"].fillna(0) * w_conv
    + df["continuity_score"].fillna(0) * w_cont
    + df["cloning_quality_score"].fillna(0) * w_qual
)
df = df.sort_values("recomputed_score", ascending=False).head(top_n)

section(f"Ranked Top {len(df)} · {quarter}")
st.dataframe(
    df[["ticker", "cusip", "recomputed_score", "consensus_score",
        "conviction_score", "continuity_score", "cloning_quality_score",
        "holder_count", "new_buy_count"]],
    use_container_width=True, hide_index=True,
    column_config={
        "ticker": st.column_config.TextColumn("TICKER", width="small"),
        "cusip": st.column_config.TextColumn("CUSIP", width="small"),
        "recomputed_score": st.column_config.ProgressColumn(
            "Recomputed", min_value=0.0, max_value=1.0, format="%.3f"),
        "consensus_score": st.column_config.NumberColumn("Cons", format="%.3f", width="small"),
        "conviction_score": st.column_config.NumberColumn("Conv", format="%.3f", width="small"),
        "continuity_score": st.column_config.NumberColumn("Cont", format="%.3f", width="small"),
        "cloning_quality_score": st.column_config.NumberColumn("Qual", format="%.3f", width="small"),
        "holder_count": st.column_config.NumberColumn("HOLDERS", format="%d", width="small"),
        "new_buy_count": st.column_config.NumberColumn("NEW", format="%d", width="small"),
    },
    height=620,
)

st.caption(
    "사이드바 슬라이더를 드래그하면 가중치가 즉시 재적용되어 순위가 갱신됩니다. Spec §6.1 default: 0.30·0.30·0.20·0.20"
)

"""Page 3: 종합 점수 랭킹 — 가중치 슬라이더로 실시간 재계산."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Signals", layout="wide")
st.title("Total Score Ranking")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM total_scores ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()
if not quarters:
    st.info("점수 데이터가 없습니다. `thirteen-f analyze`를 실행하세요.")
    st.stop()

quarter = st.sidebar.selectbox("분기", quarters)

st.sidebar.markdown("**가중치 조정** (합=1.0)")
w_cons = st.sidebar.slider("Consensus", 0.0, 1.0, 0.30, 0.05)
w_conv = st.sidebar.slider("Conviction", 0.0, 1.0, 0.30, 0.05)
w_cont = st.sidebar.slider("Continuity", 0.0, 1.0, 0.20, 0.05)
w_qual = st.sidebar.slider("Cloning Quality", 0.0, 1.0, 0.20, 0.05)
weights_sum = w_cons + w_conv + w_cont + w_qual
if abs(weights_sum - 1.0) > 0.001:
    st.sidebar.error(f"합 = {weights_sum:.2f} (1.0 권장)")

min_holders = st.sidebar.slider("Min Holders", 1, 15, 1)
top_n = st.sidebar.slider("Top N", 10, 100, 50)

# 컴포넌트 점수는 그대로 두고 클라이언트에서 가중 합 재계산
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

st.dataframe(
    df[["ticker", "cusip", "recomputed_score", "consensus_score",
        "conviction_score", "continuity_score", "cloning_quality_score",
        "holder_count", "new_buy_count"]],
    use_container_width=True, hide_index=True,
)

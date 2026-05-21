"""Page 4: 백테스트 결과 — 누적 곡선 + Drawdown + 메트릭 비교."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.charts import cumulative_curve, drawdown_chart
from thirteen_f.dashboard.tables import (
    backtest_curves_df,
    backtest_metrics_df,
    get_read_only_conn,
)

st.set_page_config(page_title="Backtest", layout="wide")
st.title("Backtest Results")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

metrics_df = backtest_metrics_df(conn)
if metrics_df.empty:
    st.info("백테스트 결과가 없습니다. `thirteen-f backtest --all`을 먼저 실행하세요.")
    st.stop()

# 전략 다중 선택
options = (metrics_df["strategy_name"] + " | " + metrics_df["run_id"].str[:8]).tolist()
selected = st.sidebar.multiselect("전략", options, default=options[:6])
selected_short_ids = [s.split(" | ")[1] for s in selected]
selected_run_ids = metrics_df[metrics_df["run_id"].str[:8].isin(selected_short_ids)]["run_id"].tolist()

if not selected_run_ids:
    st.warning("전략을 1개 이상 선택하세요.")
    st.stop()

curves = backtest_curves_df(conn, selected_run_ids)

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(cumulative_curve(curves), use_container_width=True)
with col2:
    st.plotly_chart(drawdown_chart(curves), use_container_width=True)

st.subheader("Metrics")
filtered = metrics_df[metrics_df["run_id"].isin(selected_run_ids)].copy()
display_cols = ["strategy_name", "start_date", "end_date", "cagr", "sharpe", "sortino",
                "mdd", "calmar", "win_rate_quarterly", "bench_cagr"]
for c in ["cagr", "sharpe", "sortino", "mdd", "calmar", "win_rate_quarterly", "bench_cagr"]:
    filtered[c] = filtered[c].round(4)
st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)

st.caption(
    "Spec §7.4 lookahead 가드: 모든 전략은 filed_at <= as_of_date 강제. "
    "Spec §12 한계: 45일 지연, 롱 온리, 분기 스냅샷, 기밀 처리."
)

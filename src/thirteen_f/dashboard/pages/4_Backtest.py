"""Page 4: 백테스트 결과 — 누적 곡선 + Drawdown + 메트릭 비교."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard._theme import apply_theme, kpi_card, section, status_bar
from thirteen_f.dashboard.charts import cumulative_curve, drawdown_chart
from thirteen_f.dashboard.tables import (
    backtest_curves_df,
    backtest_metrics_df,
    get_read_only_conn,
)

st.set_page_config(page_title="Backtest · 13F", page_icon="◆", layout="wide")
apply_theme()

st.title("Backtest Results")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

metrics_df = backtest_metrics_df(conn)
if metrics_df.empty:
    st.info("백테스트 결과가 없습니다. `thirteen-f backtest --all`을 먼저 실행하세요.")
    st.stop()

# Strategy multi-select
st.sidebar.markdown("### Strategies")
options = (metrics_df["strategy_name"] + " | " + metrics_df["run_id"].str[:8]).tolist()
selected = st.sidebar.multiselect("Strategies", options, default=options[:6], label_visibility="collapsed")
selected_short_ids = [s.split(" | ")[1] for s in selected]
selected_run_ids = metrics_df[metrics_df["run_id"].str[:8].isin(selected_short_ids)]["run_id"].tolist()

if not selected_run_ids:
    st.warning("전략을 1개 이상 선택하세요.")
    st.stop()

filtered = metrics_df[metrics_df["run_id"].isin(selected_run_ids)].copy()

# Status bar — best vs worst
best_cagr_idx = filtered["cagr"].idxmax()
worst_mdd_idx = filtered["mdd"].idxmax()
best_sharpe_idx = filtered["sharpe"].idxmax()
status_bar([
    ("STRATEGIES", f"{len(filtered)}", "muted"),
    ("BEST CAGR", f"{filtered.loc[best_cagr_idx, 'cagr']*100:.2f}%", "green"),
    ("BEST SHARPE", f"{filtered.loc[best_sharpe_idx, 'sharpe']:.2f}", "green"),
    ("DEEPEST MDD", f"{filtered.loc[worst_mdd_idx, 'mdd']*100:.2f}%", "red"),
    ("BENCH CAGR", f"{filtered['bench_cagr'].iloc[0]*100:.2f}%", "amber"),
])

# KPI row for best strategy
best = filtered.loc[best_sharpe_idx]
section(f"Lead Strategy by Sharpe · {best['strategy_name']}")
c1, c2, c3, c4 = st.columns(4)
with c1:
    delta = (best["cagr"] - best["bench_cagr"]) * 100
    kpi_card("CAGR", f"{best['cagr']*100:.2f}%",
             delta=f"{delta:+.2f}%p vs SPY",
             delta_color="green" if delta > 0 else "red")
with c2:
    kpi_card("Sharpe", f"{best['sharpe']:.2f}",
             delta=f"Sortino {best['sortino']:.2f}",
             delta_color="neutral")
with c3:
    kpi_card("Max Drawdown", f"{best['mdd']*100:.2f}%",
             delta=f"Calmar {best['calmar']:.2f}",
             delta_color="red")
with c4:
    kpi_card("Win Rate (Q)", f"{best['win_rate_quarterly']*100:.1f}%",
             delta=f"Total Ret {best['total_return']*100:+.1f}%",
             delta_color="green" if best['total_return'] > 0 else "red")

st.markdown("")

# Curves
curves = backtest_curves_df(conn, selected_run_ids)

col1, col2 = st.columns(2, gap="large")
with col1:
    section("Cumulative Return (normalized)")
    fig = cumulative_curve(curves)
    fig.update_layout(height=380, title=None, margin=dict(l=50, r=20, t=10, b=70))
    st.plotly_chart(fig, use_container_width=True)
with col2:
    section("Drawdown over Time")
    fig = drawdown_chart(curves)
    fig.update_layout(height=380, title=None, margin=dict(l=50, r=20, t=10, b=70))
    st.plotly_chart(fig, use_container_width=True)

# Metrics table
section("Metrics Comparison")
display_cols = ["strategy_name", "start_date", "end_date", "cagr", "sharpe", "sortino",
                "mdd", "calmar", "win_rate_quarterly", "bench_cagr"]
for c in ["cagr", "sharpe", "sortino", "mdd", "calmar", "win_rate_quarterly", "bench_cagr"]:
    filtered[c] = filtered[c].round(4)
st.dataframe(
    filtered[display_cols],
    use_container_width=True, hide_index=True,
    column_config={
        "strategy_name": st.column_config.TextColumn("STRATEGY", width="large"),
        "start_date": st.column_config.DateColumn("Start", width="small"),
        "end_date": st.column_config.DateColumn("End", width="small"),
        "cagr": st.column_config.NumberColumn("CAGR", format="%.4f", width="small"),
        "sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f", width="small"),
        "sortino": st.column_config.NumberColumn("Sortino", format="%.2f", width="small"),
        "mdd": st.column_config.NumberColumn("MDD", format="%.4f", width="small"),
        "calmar": st.column_config.NumberColumn("Calmar", format="%.2f", width="small"),
        "win_rate_quarterly": st.column_config.NumberColumn("Win Q", format="%.3f", width="small"),
        "bench_cagr": st.column_config.NumberColumn("BENCH CAGR", format="%.4f", width="small"),
    },
)

st.caption(
    "Spec §7.4 Lookahead 가드: 모든 전략은 `filings.filed_at <= as_of_date` 강제. "
    "Spec §12 한계: 45일 지연·롱 온리·분기 스냅샷·기밀 처리."
)

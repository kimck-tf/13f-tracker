"""Plotly chart builders. Streamlit/Quarto 양쪽에서 import."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def cumulative_curve(curves_df: pd.DataFrame) -> go.Figure:
    """backtest_curves DataFrame (run_id, date, nav, benchmark_nav, position_count)."""
    fig = go.Figure()
    for run_id, grp in curves_df.groupby("run_id"):
        grp = grp.sort_values("date")
        norm = grp["nav"] / grp["nav"].iloc[0]
        # 전략 이름이 있으면 사용, 없으면 run_id 8자
        label = grp.get("strategy_name", pd.Series([run_id])).iloc[0] if "strategy_name" in grp.columns else run_id
        fig.add_trace(go.Scatter(
            x=grp["date"], y=norm, name=str(label), mode="lines"
        ))
    # 벤치마크 (한 번만)
    if not curves_df.empty:
        first_run = curves_df["run_id"].iloc[0]
        bench = curves_df[curves_df["run_id"] == first_run].sort_values("date")
        bench_norm = bench["benchmark_nav"] / bench["benchmark_nav"].iloc[0]
        fig.add_trace(go.Scatter(
            x=bench["date"], y=bench_norm, name="Benchmark (SPY)",
            mode="lines", line=dict(dash="dash", color="black")
        ))
    fig.update_layout(
        title="Cumulative Return", xaxis_title="Date", yaxis_title="Normalized NAV",
        height=400, legend=dict(orientation="h", y=-0.2),
    )
    return fig


def drawdown_chart(curves_df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for run_id, grp in curves_df.groupby("run_id"):
        grp = grp.sort_values("date").copy()
        peak = grp["nav"].cummax()
        dd = -(peak - grp["nav"]) / peak
        label = grp.get("strategy_name", pd.Series([run_id])).iloc[0] if "strategy_name" in grp.columns else run_id
        fig.add_trace(go.Scatter(
            x=grp["date"], y=dd, name=str(label), mode="lines", fill="tozeroy",
        ))
    fig.update_layout(
        title="Drawdown", xaxis_title="Date", yaxis_title="Drawdown",
        yaxis_tickformat=".0%", height=300,
    )
    return fig


def consensus_heatmap(matrix: pd.DataFrame) -> go.Figure:
    """matrix: rows=tickers, cols=manager labels, values=weight or 1/0."""
    # 다크 테마용 커스텀 스케일 (배경 + accent green)
    scale = [
        [0.0, "#0F1722"],
        [0.15, "#143A3A"],
        [0.4, "#0F7060"],
        [0.7, "#00C896"],
        [1.0, "#7AF0C8"],
    ]
    fig = px.imshow(
        matrix, color_continuous_scale=scale, aspect="auto",
        labels=dict(color="weight"),
    )
    fig.update_layout(title="Consensus Heatmap", height=600)
    return fig


def change_waterfall(counts: dict[str, int]) -> go.Figure:
    """counts: {change_type: count}. 다크 테마 + 의미별 컬러."""
    order = ["new", "increase", "hold", "decrease", "exit"]
    color_map = {
        "new": "#00C896",       # accent green
        "increase": "#5EA2EF",  # blue (포지션 추가)
        "hold": "#6B7785",      # muted (변화 없음)
        "decrease": "#F5A623",  # amber (경고)
        "exit": "#FF3B5C",      # accent red
    }
    keys = [k for k in order if k in counts]
    fig = go.Figure(go.Bar(
        x=keys,
        y=[counts[k] for k in keys],
        marker_color=[color_map[k] for k in keys],
        marker_line_width=0,
        text=[f"{counts[k]:,}" for k in keys],
        textposition="outside",
        textfont=dict(family="IBM Plex Mono, monospace", size=11, color="#E6EAF0"),
    ))
    fig.update_layout(title="Change Type Distribution", height=300, showlegend=False)
    return fig


def portfolio_treemap(weights: dict[str, float], label_col: str = "Ticker") -> go.Figure:
    fig = px.treemap(
        names=list(weights.keys()),
        parents=[""] * len(weights),
        values=list(weights.values()),
    )
    fig.update_layout(title=f"Portfolio Weights ({label_col})", height=500)
    return fig

"""Page 5: 거장간 비교 — 공통 보유 매트릭스 + cosine 유사도."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard._theme import COLORS, apply_theme, section, sidebar_toggle, status_bar
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Compare · 13F", page_icon="◆", layout="wide")
apply_theme()
sidebar_toggle()

st.title("Compare Managers")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

managers = conn.execute("SELECT cik, label FROM managers ORDER BY label").fetchdf()
if managers.empty:
    st.stop()

st.sidebar.markdown("### Managers · 2명+")
selected = st.sidebar.multiselect(
    "Managers",
    managers["label"].tolist(),
    default=managers["label"].tolist()[:3],
    label_visibility="collapsed",
)
if len(selected) < 2:
    st.warning("2명 이상 선택하세요.")
    st.stop()

ciks = managers[managers["label"].isin(selected)]["cik"].tolist()
quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM signals_quarterly ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()
st.sidebar.markdown("### Quarter")
quarter = st.sidebar.selectbox("Quarter", quarters, label_visibility="collapsed")

# Fetch weight_pct vectors
placeholders = ",".join("?" for _ in ciks)
df = conn.execute(
    f"""
    SELECT s.cik, mn.label, s.cusip, s.weight_pct
    FROM signals_quarterly s
    JOIN managers mn ON mn.cik = s.cik
    WHERE s.cik IN ({placeholders}) AND s.period_of_report = ? AND s.change_type != 'exit'
    """,
    [*ciks, quarter],
).fetchdf()

if df.empty:
    st.warning("선택한 분기/거장에 데이터가 없습니다.")
    st.stop()

matrix = df.pivot_table(index="cusip", columns="label", values="weight_pct", fill_value=0)

# Status bar
status_bar([
    ("QUARTER", str(quarter), "amber"),
    ("MANAGERS", f"{len(selected)}", "muted"),
    ("UNIQUE CUSIPS", f"{len(matrix):,}", "muted"),
])

# Cosine 유사도 계산
labels = matrix.columns.tolist()
vectors = matrix.to_numpy()


def cosine(a, b):
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


sim = pd.DataFrame(
    [[cosine(vectors[:, i], vectors[:, j]) for j in range(len(labels))] for i in range(len(labels))],
    index=labels, columns=labels,
)

# Cosine heatmap
col1, col2 = st.columns([1, 1], gap="large")
with col1:
    section("Portfolio Cosine Similarity")
    fig = go.Figure(go.Heatmap(
        z=sim.values,
        x=labels, y=labels,
        text=sim.round(3).values,
        texttemplate="%{text}",
        textfont={"family": "IBM Plex Mono, monospace", "size": 11, "color": COLORS["text_primary"]},
        colorscale=[
            [0.0, COLORS["bg_base"]],
            [0.5, COLORS["accent_blue"]],
            [1.0, COLORS["accent_green"]],
        ],
        zmin=0.0, zmax=1.0,
        showscale=True,
        colorbar=dict(thickness=10, len=0.7, tickfont=dict(size=10, color=COLORS["text_muted"])),
    ))
    fig.update_layout(
        height=440,
        margin=dict(l=80, r=10, t=10, b=60),
        xaxis=dict(side="bottom"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

with col2:
    section("Common Holdings Matrix · Top 50 weights")
    st.dataframe(
        matrix.head(50),
        use_container_width=True,
        height=440,
        column_config={
            col: st.column_config.NumberColumn(col, format="%.3f", width="small")
            for col in matrix.columns
        },
    )

st.caption(
    "Spec §8.1: 두 거장의 weight_pct 벡터 (CUSIP 차원, 미보유=0)의 cosine. "
    "1.0=동일 포트폴리오, 0.0=공통 보유 없음."
)

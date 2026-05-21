"""Page 5: 거장간 비교 — 공통 보유 매트릭스 + cosine 유사도."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.tables import get_read_only_conn

st.set_page_config(page_title="Compare", layout="wide")
st.title("Compare Managers")

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))

managers = conn.execute("SELECT cik, label FROM managers ORDER BY label").fetchdf()
if managers.empty:
    st.stop()

selected = st.sidebar.multiselect(
    "거장 (2명 이상)", managers["label"].tolist(),
    default=managers["label"].tolist()[:3],
)
if len(selected) < 2:
    st.warning("2명 이상 선택하세요.")
    st.stop()

ciks = managers[managers["label"].isin(selected)]["cik"].tolist()
quarters = conn.execute(
    "SELECT DISTINCT period_of_report FROM signals_quarterly ORDER BY period_of_report DESC"
).fetchdf()["period_of_report"].tolist()
quarter = st.sidebar.selectbox("분기", quarters)

# weight_pct 벡터 추출 (Spec §8.1: CUSIP 차원, 미보유=0)
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

st.subheader("Common Holdings Matrix")
st.dataframe(matrix.head(50), use_container_width=True)

# Cosine 유사도
labels = matrix.columns.tolist()
vectors = matrix.to_numpy()  # rows = cusip, cols = manager


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

st.subheader("Portfolio Cosine Similarity")
st.dataframe(sim.round(3), use_container_width=True)
st.caption("Spec §8.1: 두 거장의 weight_pct 벡터 (CUSIP 차원, 미보유=0)의 cosine.")

"""Streamlit 홈 페이지: 최신 분기 헤드라인 + 거장 활동."""
from __future__ import annotations

import streamlit as st

from thirteen_f.core.config import load_settings
from thirteen_f.dashboard.tables import (
    get_read_only_conn,
    latest_period,
    manager_list,
    top_scores,
)


st.set_page_config(page_title="13F Tracker", layout="wide")
st.title("13F Portfolio Tracker")
st.caption(
    "본 도구의 시그널은 13F 데이터의 구조적 한계(45일 지연·롱 온리·분기 스냅샷·기밀 처리)를 "
    "전제로 합니다. 모든 결과는 참고용."
)

settings = load_settings()
conn = get_read_only_conn(str(settings.duckdb_path))


@st.cache_data(ttl=600)
def _top_signals(period_iso: str):
    from datetime import date
    p = date.fromisoformat(period_iso)
    return top_scores(conn, p, top_n=10)


@st.cache_data(ttl=600)
def _managers():
    return manager_list(conn)


period = latest_period(conn)

col1, col2 = st.columns(2)
with col1:
    st.subheader("최신 분기")
    st.metric("Period", str(period) if period else "데이터 없음")
    st.subheader("거장")
    st.dataframe(_managers(), use_container_width=True, hide_index=True)

with col2:
    st.subheader("이번 분기 종합 점수 Top 10")
    if period:
        st.dataframe(
            _top_signals(period.isoformat()),
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("아직 데이터가 없습니다. `thirteen-f collect → analyze`를 먼저 실행하세요.")

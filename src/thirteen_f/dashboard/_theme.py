"""Streamlit 디자인 시스템 — Bloomberg/Robinhood quiet finance tone.

각 페이지 상단에서 `apply_theme()` 호출하면 다음이 적용됨:
- IBM Plex Sans / Mono + Fraunces (Google Fonts)
- 다크 베이스 색상 토큰 + grain texture overlay
- Plotly default template = "fnc"
- KPI / status bar / ticker badge 커스텀 컴포넌트

Streamlit 기본 components는 한계가 있어 raw HTML/CSS 주입을 적극 활용.
"""
from __future__ import annotations

import streamlit as st


# ---- Design tokens ----
COLORS = {
    "bg_base": "#0A0E14",
    "bg_surface": "#13181F",
    "bg_elevated": "#181F28",
    "border_line": "#1F2630",
    "border_strong": "#2A3340",
    "text_primary": "#E6EAF0",
    "text_secondary": "#9BA5B4",
    "text_muted": "#6B7785",
    "accent_green": "#00C896",
    "accent_red": "#FF3B5C",
    "accent_blue": "#4A9EFF",
    "accent_amber": "#F5A623",
    "accent_violet": "#A78BFA",
}


_GOOGLE_FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500;600&family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500&display=swap" rel="stylesheet">
"""


def _css() -> str:
    c = COLORS
    return f"""
<style>
:root {{
    --bg-base: {c['bg_base']};
    --bg-surface: {c['bg_surface']};
    --bg-elevated: {c['bg_elevated']};
    --border-line: {c['border_line']};
    --border-strong: {c['border_strong']};
    --text-primary: {c['text_primary']};
    --text-secondary: {c['text_secondary']};
    --text-muted: {c['text_muted']};
    --accent-green: {c['accent_green']};
    --accent-red: {c['accent_red']};
    --accent-blue: {c['accent_blue']};
    --accent-amber: {c['accent_amber']};
    --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
    --font-mono: 'IBM Plex Mono', 'SF Mono', Monaco, monospace;
    --font-display: 'Fraunces', 'Georgia', serif;
}}

/* === Base === */
html, body, [class*="st-"], [class*="css-"] {{
    font-family: var(--font-sans) !important;
}}

.stApp {{
    background: linear-gradient(180deg, var(--bg-base) 0%, #0C1118 60%, #0A0E14 100%) !important;
    color: var(--text-primary);
}}

/* Grain texture overlay — 미묘한 노이즈로 디지털 단말 질감 */
.stApp::before {{
    content: '';
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feComponentTransfer><feFuncA type='linear' slope='0.05'/></feComponentTransfer></filter><rect width='100%' height='100%' filter='url(%23n)' opacity='1'/></svg>");
    opacity: 0.5;
    z-index: 0;
    mix-blend-mode: overlay;
}}

/* Main container — 정보 밀도 */
.block-container {{
    padding-top: 1.25rem !important;
    padding-bottom: 2rem !important;
    max-width: 1480px !important;
}}

/* === Typography === */
h1 {{
    font-family: var(--font-display) !important;
    font-weight: 400 !important;
    letter-spacing: -0.018em !important;
    color: var(--text-primary) !important;
    border-bottom: 1px solid var(--border-line);
    padding-bottom: 0.5rem !important;
    margin-bottom: 1.25rem !important;
    font-size: 2.1rem !important;
    line-height: 1.15 !important;
}}

h2, h3, h4 {{
    font-family: var(--font-sans) !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.005em !important;
}}

h2 {{ font-size: 1.05rem !important; font-weight: 600 !important; margin-top: 1.5rem !important; }}
h3 {{ font-size: 0.92rem !important; font-weight: 600 !important; }}
h4 {{ font-size: 0.85rem !important; font-weight: 600 !important; color: var(--text-muted) !important; text-transform: uppercase; letter-spacing: 0.08em !important; }}

p, li, .stMarkdown {{
    color: var(--text-secondary) !important;
    font-size: 13px !important;
    line-height: 1.55 !important;
}}

strong, b {{ color: var(--text-primary) !important; }}

/* === DataFrame — 모노스페이스 숫자 === */
[data-testid="stDataFrame"] {{
    border: 1px solid var(--border-line);
    border-radius: 4px;
    background: var(--bg-surface);
}}
[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] {{
    background: var(--bg-surface) !important;
}}
[data-testid="stDataFrame"] table {{
    font-family: var(--font-mono) !important;
    font-size: 12.5px !important;
    font-variant-numeric: tabular-nums !important;
}}

/* === Metric (Streamlit 기본) === */
[data-testid="stMetric"] {{
    background: var(--bg-surface);
    border: 1px solid var(--border-line);
    border-radius: 4px;
    padding: 14px 16px !important;
}}
[data-testid="stMetricLabel"] p {{
    color: var(--text-muted) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}}
[data-testid="stMetricValue"] {{
    font-family: var(--font-mono) !important;
    font-size: 24px !important;
    font-weight: 500 !important;
    color: var(--text-primary) !important;
    font-variant-numeric: tabular-nums !important;
    line-height: 1.2 !important;
}}
[data-testid="stMetricDelta"] {{
    font-family: var(--font-mono) !important;
    font-size: 12px !important;
    font-variant-numeric: tabular-nums !important;
}}

/* === Sidebar === */
[data-testid="stSidebar"] {{
    background: #0B0F15 !important;
    border-right: 1px solid var(--border-line);
}}
[data-testid="stSidebar"] .stMarkdown p {{
    font-size: 10.5px !important;
    color: var(--text-muted) !important;
}}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stMultiSelect label {{
    color: var(--text-muted) !important;
    font-size: 10.5px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
}}

/* Selectbox/dropdown */
[data-baseweb="select"] > div {{
    background: var(--bg-surface) !important;
    border-color: var(--border-line) !important;
    font-family: var(--font-mono) !important;
    font-size: 13px !important;
}}

/* Slider */
.stSlider [data-baseweb="slider"] > div {{
    background: var(--border-line) !important;
}}
.stSlider [role="slider"] {{
    background: var(--accent-green) !important;
}}

/* === Plotly chart container === */
[data-testid="stPlotlyChart"] {{
    background: var(--bg-surface);
    border: 1px solid var(--border-line);
    border-radius: 4px;
    padding: 6px;
}}

/* === Caption === */
.stCaption, [data-testid="stCaption"], [data-testid="stCaptionContainer"] {{
    color: var(--text-muted) !important;
    font-size: 11.5px !important;
    line-height: 1.5 !important;
}}

/* === Code / inline === */
code {{
    font-family: var(--font-mono) !important;
    background: var(--bg-elevated) !important;
    color: var(--accent-amber) !important;
    border-radius: 3px;
    padding: 1px 5px;
    font-size: 12px !important;
}}

/* === Alert / info === */
[data-testid="stAlert"] {{
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-line) !important;
    border-left: 3px solid var(--accent-blue) !important;
    color: var(--text-secondary) !important;
    border-radius: 4px;
}}
[data-testid="stAlert"][kind="warning"] {{ border-left-color: var(--accent-amber) !important; }}
[data-testid="stAlert"][kind="error"] {{ border-left-color: var(--accent-red) !important; }}
[data-testid="stAlert"][kind="success"] {{ border-left-color: var(--accent-green) !important; }}

/* === Tabs === */
.stTabs [data-baseweb="tab-list"] {{
    border-bottom: 1px solid var(--border-line);
    gap: 0 !important;
    background: transparent !important;
}}
.stTabs [data-baseweb="tab"] {{
    color: var(--text-muted) !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    padding: 10px 18px !important;
    background: transparent !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}}
.stTabs [aria-selected="true"] {{
    color: var(--text-primary) !important;
    border-bottom: 2px solid var(--accent-green) !important;
}}

/* === HR === */
hr {{
    border-color: var(--border-line) !important;
    margin: 1.5rem 0 !important;
}}

/* === Custom: status bar === */
.fnc-statusbar {{
    display: flex;
    flex-wrap: wrap;
    gap: 32px;
    padding: 8px 0 16px 0;
    border-bottom: 1px solid var(--border-line);
    margin-bottom: 22px;
    font-family: var(--font-mono);
}}
.fnc-statusbar .item {{ display: flex; flex-direction: column; gap: 3px; min-width: 80px; }}
.fnc-statusbar .label {{
    color: var(--text-muted);
    font-size: 9.5px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-family: var(--font-sans);
    font-weight: 600;
}}
.fnc-statusbar .value {{
    color: var(--text-primary);
    font-size: 15px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
}}
.fnc-statusbar .value.green {{ color: var(--accent-green); }}
.fnc-statusbar .value.red {{ color: var(--accent-red); }}
.fnc-statusbar .value.amber {{ color: var(--accent-amber); }}
.fnc-statusbar .value.muted {{ color: var(--text-secondary); }}

/* === Custom: KPI card === */
.fnc-kpi {{
    background: var(--bg-surface);
    border: 1px solid var(--border-line);
    border-radius: 4px;
    padding: 16px 18px;
    transition: border-color 0.12s ease, background 0.12s ease;
}}
.fnc-kpi:hover {{
    border-color: var(--border-strong);
    background: var(--bg-elevated);
}}
.fnc-kpi .label {{
    color: var(--text-muted);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 8px;
}}
.fnc-kpi .value {{
    font-family: var(--font-mono);
    font-size: 26px;
    font-weight: 500;
    line-height: 1.1;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.01em;
}}
.fnc-kpi .delta {{
    font-family: var(--font-mono);
    font-size: 12px;
    margin-top: 6px;
    font-variant-numeric: tabular-nums;
    font-weight: 500;
}}
.fnc-kpi .delta.green {{ color: var(--accent-green); }}
.fnc-kpi .delta.red {{ color: var(--accent-red); }}
.fnc-kpi .delta.neutral {{ color: var(--text-muted); }}

/* === Custom: ticker badge === */
.fnc-ticker {{
    display: inline-block;
    font-family: var(--font-mono);
    font-weight: 600;
    font-size: 11px;
    padding: 2px 6px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-line);
    border-radius: 3px;
    color: var(--text-primary);
    letter-spacing: 0.02em;
}}

/* === Section header — 작은 캡스 === */
.fnc-section {{
    font-family: var(--font-sans);
    font-size: 10.5px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-weight: 600;
    margin: 18px 0 10px 0;
    padding-bottom: 4px;
    border-bottom: 1px dotted var(--border-line);
}}

/* === Streamlit chrome === */
#MainMenu, footer {{ visibility: hidden !important; }}
[data-testid="stToolbar"] {{ display: none !important; }}
header[data-testid="stHeader"] {{
    background: rgba(19, 24, 31, 0.85) !important;
    border-bottom: 1px solid var(--border-line) !important;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    min-height: 2.75rem !important;
    z-index: 99 !important;
}}

/* === Sidebar — collapse 동작 무력화 ===
 * Streamlit 1.57이 사이드바 닫힘을 `transform: translateX(-300px)`로 처리하는데,
 * 그 안의 collapse 버튼도 함께 화면 밖으로 밀려나서 다시 열 방법이 없어짐.
 * → transform: none 강제 + width 고정으로 항상 펼침 상태 유지.
 * 사용자가 collapse 버튼을 눌러도 시각적으로 닫히지 않음 (의도된 fix).
 */
[data-testid="stSidebar"] {{
    transform: none !important;
    visibility: visible !important;
    min-width: 16rem !important;
}}

/* sidebar 안의 collapse 버튼은 항상 visible + 강조 (눌러도 안 닫히지만 버튼은 유지) */
[data-testid="stSidebarCollapseButton"] {{
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
}}
[data-testid="stSidebarCollapseButton"] button,
button[kind="headerNoPadding"],
[data-testid="stBaseButton-headerNoPadding"] {{
    background: var(--bg-elevated) !important;
    border: 1px solid var(--border-line) !important;
    border-radius: 4px !important;
    color: var(--text-secondary) !important;
    padding: 4px 6px !important;
    transition: background 0.12s ease, border-color 0.12s ease;
}}
[data-testid="stSidebarCollapseButton"] button:hover {{
    background: var(--accent-green) !important;
    border-color: var(--accent-green) !important;
    color: var(--bg-base) !important;
}}
[data-testid="stSidebarCollapseButton"] svg,
button[kind="headerNoPadding"] svg {{
    fill: currentColor !important;
    color: inherit !important;
}}
[data-testid="stSidebarCollapseButton"] span,
button[kind="headerNoPadding"] span {{
    color: inherit !important;
    font-size: 18px !important;
}}

/* Sidebar — section title 작게 */
[data-testid="stSidebar"] .stMarkdown h1,
[data-testid="stSidebar"] .stMarkdown h2,
[data-testid="stSidebar"] .stMarkdown h3 {{
    font-size: 10px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.14em !important;
    color: var(--text-muted) !important;
    font-family: var(--font-sans) !important;
    font-weight: 600 !important;
    border: none !important;
    padding: 0 !important;
    margin: 1rem 0 0.4rem 0 !important;
}}
</style>
"""


def apply_theme() -> None:
    """모든 페이지 상단에서 호출. CSS 주입 + Plotly template 등록."""
    st.markdown(_GOOGLE_FONTS, unsafe_allow_html=True)
    st.markdown(_css(), unsafe_allow_html=True)
    _register_plotly_template()


def _register_plotly_template() -> None:
    """Plotly 차트 통일 템플릿 등록 (default로 설정)."""
    import plotly.io as pio
    c = COLORS
    template = {
        "layout": {
            "paper_bgcolor": c["bg_surface"],
            "plot_bgcolor": c["bg_surface"],
            "font": {
                "family": "IBM Plex Sans, sans-serif",
                "color": c["text_primary"],
                "size": 12,
            },
            "colorway": [
                c["accent_green"], c["accent_blue"], c["accent_amber"],
                c["accent_violet"], c["accent_red"],
                "#5EA2EF", "#FFB266", "#7AD9A8", "#E47CFF", "#FF8FA3",
            ],
            "xaxis": {
                "gridcolor": c["border_line"],
                "linecolor": c["border_line"],
                "zerolinecolor": c["border_line"],
                "tickfont": {"family": "IBM Plex Mono, monospace", "size": 10.5, "color": c["text_muted"]},
                "title": {"font": {"size": 11, "color": c["text_muted"]}},
            },
            "yaxis": {
                "gridcolor": c["border_line"],
                "linecolor": c["border_line"],
                "zerolinecolor": c["border_line"],
                "tickfont": {"family": "IBM Plex Mono, monospace", "size": 10.5, "color": c["text_muted"]},
                "title": {"font": {"size": 11, "color": c["text_muted"]}},
            },
            "legend": {
                "bgcolor": "rgba(0,0,0,0)",
                "font": {"size": 11, "color": c["text_secondary"]},
                "bordercolor": c["border_line"],
            },
            "margin": {"l": 50, "r": 20, "t": 40, "b": 40},
            "hoverlabel": {
                "bgcolor": c["bg_elevated"],
                "bordercolor": c["border_strong"],
                "font": {
                    "family": "IBM Plex Mono, monospace",
                    "size": 12,
                    "color": c["text_primary"],
                },
            },
        }
    }
    pio.templates["fnc"] = template
    pio.templates.default = "fnc"


# ---- Custom Streamlit components ----

def status_bar(items: list[tuple[str, str, str]]) -> None:
    """상단 헤더 status bar.

    Args:
        items: [(label, value, color_class), ...]. color_class: "", "green", "red", "amber", "muted"
    """
    parts = []
    for label, value, cls in items:
        color_class = f" {cls}" if cls else ""
        parts.append(
            f'<div class="item"><div class="label">{label}</div>'
            f'<div class="value{color_class}">{value}</div></div>'
        )
    st.markdown(
        f'<div class="fnc-statusbar">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, delta: str | None = None, delta_color: str = "neutral") -> None:
    """KPI 카드 (st.metric 대체).

    Args:
        delta_color: "green", "red", "neutral"
    """
    delta_html = (
        f'<div class="delta {delta_color}">{delta}</div>' if delta else ""
    )
    st.markdown(
        f'<div class="fnc-kpi"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>{delta_html}</div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    """작은 캡스 섹션 헤더."""
    st.markdown(f'<div class="fnc-section">{title}</div>', unsafe_allow_html=True)


def ticker_badge(ticker: str) -> str:
    """티커 뱃지 HTML — markdown 안에 inline 사용."""
    return f'<span class="fnc-ticker">{ticker}</span>'


def sidebar_toggle() -> None:
    """사이드바 표시/숨김 토글 — 모든 페이지 상단에서 호출.

    session_state['fnc_sidebar_hidden'] 로 상태 관리. 페이지 이동·새로고침 시:
    - 사이드바 안: "◀ 사이드바 숨김" 버튼
    - 사이드바 숨김 시 메인 영역 좌측 상단: "사이드바 표시 ▶" 버튼

    Streamlit native sidebar collapse는 transform 기반이라 한 번 닫으면 다시
    못 여는 문제 (Streamlit 1.57) 가 있어, _theme.py에서 사이드바 transform을
    무력화하고 우리 자체 토글로 대체.
    """
    if "fnc_sidebar_hidden" not in st.session_state:
        st.session_state.fnc_sidebar_hidden = False

    if st.session_state.fnc_sidebar_hidden:
        # 1. 사이드바 숨김용 CSS 주입 (디스플레이 none)
        st.markdown(
            """
            <style>
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stSidebar"] + section { margin-left: 0 !important; }
            section[data-testid="stMain"] {
                padding-left: 0 !important;
                margin-left: 0 !important;
            }
            .block-container { padding-left: 2.5rem !important; }
            </style>
            """,
            unsafe_allow_html=True,
        )
        # 2. 메인 영역 좌측 상단에 "표시" 버튼
        col_btn, _ = st.columns([1, 11])
        with col_btn:
            if st.button(
                "▶ Show",
                key="fnc_sb_show_btn",
                help="사이드바 다시 표시 (Show sidebar)",
                use_container_width=True,
            ):
                st.session_state.fnc_sidebar_hidden = False
                st.rerun()
    else:
        # 사이드바 안 가장 위에 "숨김" 버튼
        with st.sidebar:
            if st.button(
                "◀ Hide Sidebar",
                key="fnc_sb_hide_btn",
                help="본문 공간 확장",
                use_container_width=True,
            ):
                st.session_state.fnc_sidebar_hidden = True
                st.rerun()

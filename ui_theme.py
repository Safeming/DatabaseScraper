"""AI-Scraper 视觉主题。
设计语言: 把"数据库 schema"作为主视觉,每页是一次"查询"。
- 配色: 冷灰底 + 深蓝墨 + 靛紫主色 + 珊瑚强调
- 字体: IBM Plex Sans + IBM Plex Mono
- 签名元素: 数据流水线指示器(对应 pipeline.py 真实阶段)
"""
from __future__ import annotations

import streamlit as st


# ─── 设计 token ───
COLOR_BG = "#F4F6FA"
COLOR_SURFACE = "#FFFFFF"
COLOR_INK = "#0E1B33"
COLOR_INK_MUTED = "#5A6B86"
COLOR_BORDER = "#E1E6EE"
COLOR_PRIMARY = "#4F2DD8"   # indigo
COLOR_ACCENT = "#FF5C5C"    # coral
COLOR_SUCCESS = "#0AA66E"
COLOR_WARN = "#F0A842"

# 真实流水线阶段(对应 pipeline.py: stage_scrape / classify_website / stage_extract / stage_store)
STAGES: list[tuple[str, str]] = [
    ("scrape",   "抓取"),
    ("classify", "AI识别"),
    ("extract",  "提取"),
    ("store",    "入库"),
    ("explore",  "浏览"),
    ("analyze",  "分析"),
]


def apply_theme(page_title: str = "AI-Scraper", page_icon: str = "▣"):
    """每页第一行调用一次。负责 set_page_config + 注入 CSS。"""
    # set_page_config 必须是第一个 streamlit 调用
    if not st.session_state.get("_page_config_set"):
        st.set_page_config(
            page_title=page_title,
            page_icon=page_icon,
            layout="wide",
            initial_sidebar_state="expanded",
            menu_items={},
        )
        st.session_state["_page_config_set"] = True

    if st.session_state.get("_theme_css_injected"):
        return
    st.session_state["_theme_css_injected"] = True

    st.markdown(_build_css(), unsafe_allow_html=True)


def page_header(
    eyebrow: str,
    title: str,
    subtitle: str = "",
    active_stage: str = "",
):
    """渲染统一的页面头部:面包屑 eyebrow + 主标题 + 副标题 + 数据流指示器。

    :param eyebrow: 路径式标签,如 "books" / "jobs / history"
    :param title: 主标题
    :param subtitle: 副标题(可选)
    :param active_stage: STAGES 中的某个 code,该阶段会高亮。空字符串则无高亮
    """
    chips_html = []
    for i, (code, label) in enumerate(STAGES):
        cls = "stage stage--active" if code == active_stage else "stage"
        chips_html.append(
            f'<span class="{cls}"><span class="stage__num">0{i+1}</span><span>{label}</span></span>'
        )
    flow_html = "".join(chips_html)

    sub_html = f'<p class="page-header__subtitle">{subtitle}</p>' if subtitle else ""

    st.markdown(
        f"""
        <div class="page-header">
          <div class="page-header__eyebrow">› ai_scraper_db / {eyebrow}</div>
          <h1 class="page-header__title">{title}</h1>
          {sub_html}
          <div class="stage-flow">{flow_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, eyebrow: str = ""):
    """章节小标题:Plex Mono eyebrow + 主标题。"""
    eb = f'<div class="section__eyebrow">{eyebrow}</div>' if eyebrow else ""
    st.markdown(
        f'<div class="section-header">{eb}<h2 class="section__title">{title}</h2></div>',
        unsafe_allow_html=True,
    )


def stat_card(label: str, value: str | int, hint: str = ""):
    """KPI 卡片(替代 st.metric,样式可控)。"""
    hint_html = f'<div class="stat__hint">{hint}</div>' if hint else ""
    st.markdown(
        f"""
        <div class="stat-card">
          <div class="stat__label">{label}</div>
          <div class="stat__value">{value}</div>
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─── 内部 CSS 字符串(分块为了可读) ───

def _build_css() -> str:
    return _CSS_FONTS + _CSS_RESET + _CSS_HEADER + _CSS_FLOW + _CSS_WIDGETS + _CSS_SECTION + _CSS_STAT


_CSS_FONTS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

html, body, [class*="css"], .main, .block-container, [data-testid="stAppViewContainer"] {
    font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
code, pre, .stCode, [class*="language-"] {
    font-family: 'IBM Plex Mono', 'JetBrains Mono', Menlo, Consolas, monospace !important;
}
</style>
"""

_CSS_RESET = f"""
<style>
/* 隐藏 streamlit 默认 chrome */
[data-testid="stToolbar"], .stDeployButton, #MainMenu, header {{
    display: none !important;
    visibility: hidden !important;
}}
[data-testid="stAppViewContainer"] {{ background: {COLOR_BG} !important; }}
[data-testid="stSidebar"] {{
    background: {COLOR_SURFACE} !important;
    border-right: 1px solid {COLOR_BORDER};
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    color: {COLOR_INK_MUTED} !important;
    border-radius: 6px;
    padding: 6px 12px !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{
    background: {COLOR_BG} !important;
    color: {COLOR_INK} !important;
}}
[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: {COLOR_INK} !important;
    color: #FFFFFF !important;
    font-weight: 500;
}}
.block-container {{
    padding-top: 1.5rem !important;
    max-width: 1280px !important;
}}
hr {{ border-color: {COLOR_BORDER} !important; opacity: 0.6; }}

/* 移除 markdown headers 默认样式接管 */
.block-container h1, .block-container h2, .block-container h3 {{
    color: {COLOR_INK};
    font-weight: 600;
    letter-spacing: -0.01em;
}}
</style>
"""

_CSS_HEADER = f"""
<style>
.page-header {{
    margin: 0 0 32px 0;
    padding: 28px 0 24px;
    border-bottom: 1px solid {COLOR_BORDER};
}}
.page-header__eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    font-weight: 500;
    color: {COLOR_INK_MUTED};
    letter-spacing: 0.04em;
    margin-bottom: 12px;
    text-transform: lowercase;
}}
.page-header__title {{
    font-size: 36px;
    font-weight: 600;
    color: {COLOR_INK};
    margin: 0 0 8px 0;
    letter-spacing: -0.02em;
    line-height: 1.1;
}}
.page-header__subtitle {{
    font-size: 15px;
    color: {COLOR_INK_MUTED};
    margin: 0 0 20px 0;
    max-width: 720px;
    line-height: 1.5;
}}
</style>
"""

_CSS_FLOW = f"""
<style>
.stage-flow {{
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 6px;
    margin-top: 18px;
    padding: 0;
    line-height: 1;
}}
.stage {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    font-weight: 500;
    color: {COLOR_INK_MUTED};
    background: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 4px;
    white-space: nowrap;
    transition: all 0.15s ease;
}}
.stage__num {{
    font-size: 10px;
    color: {COLOR_BORDER};
    font-weight: 600;
    letter-spacing: 0.05em;
}}
.stage--active {{
    color: {COLOR_SURFACE};
    background: {COLOR_INK};
    border-color: {COLOR_INK};
}}
.stage--active .stage__num {{
    color: {COLOR_ACCENT};
}}
.stage__sep {{
    display: inline-flex;
    align-items: center;
    color: {COLOR_BORDER};
    font-family: 'IBM Plex Mono', monospace;
    font-size: 14px;
    user-select: none;
}}
</style>
"""

_CSS_WIDGETS = f"""
<style>
/* 按钮 — 主色 */
.stButton > button {{
    background: {COLOR_INK} !important;
    color: {COLOR_SURFACE} !important;
    border: none !important;
    border-radius: 4px !important;
    font-weight: 500 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    padding: 8px 18px !important;
    transition: all 0.12s ease;
}}
.stButton > button:hover {{
    background: {COLOR_PRIMARY} !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(79, 45, 216, 0.2);
}}
.stButton > button:active {{ transform: translateY(0); }}

/* 表单元素 */
.stTextInput input, .stTextArea textarea, .stSelectbox > div > div, .stNumberInput input {{
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 4px !important;
    background: {COLOR_SURFACE} !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}}
.stTextInput input:focus, .stTextArea textarea:focus {{
    border-color: {COLOR_PRIMARY} !important;
    box-shadow: 0 0 0 3px rgba(79, 45, 216, 0.1) !important;
}}
.stTextArea textarea {{ font-family: 'IBM Plex Mono', monospace !important; }}

/* 标签 */
[data-testid="stWidgetLabel"], label {{
    color: {COLOR_INK} !important;
    font-weight: 500 !important;
    font-size: 13px !important;
}}

/* dataframe */
[data-testid="stDataFrame"] {{
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    overflow: hidden;
}}
/* dataframe 内的图片缩略图 — 细边框 + 圆角 */
[data-testid="stDataFrame"] img {{
    border-radius: 4px;
    border: 1px solid {COLOR_BORDER};
    object-fit: cover;
    background: {COLOR_BG};
}}

/* expander */
[data-testid="stExpander"] {{
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 6px !important;
    background: {COLOR_SURFACE} !important;
    box-shadow: none !important;
}}
[data-testid="stExpander"] summary {{
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 13px !important;
    color: {COLOR_INK} !important;
}}

/* code 块 */
.stCode {{
    background: #0E1B33 !important;
    border-radius: 6px !important;
    padding: 12px !important;
}}
.stCode code, .stCode pre {{
    background: transparent !important;
    color: #E5EAF3 !important;
    font-size: 13px !important;
}}

/* alert */
[data-testid="stAlert"] {{
    border-radius: 6px !important;
    border-left: 3px solid {COLOR_PRIMARY} !important;
    background: {COLOR_SURFACE} !important;
}}
[data-testid="stNotificationContentSuccess"] {{ border-left-color: {COLOR_SUCCESS} !important; }}
[data-testid="stNotificationContentError"] {{ border-left-color: {COLOR_ACCENT} !important; }}
[data-testid="stNotificationContentWarning"] {{ border-left-color: {COLOR_WARN} !important; }}

/* tabs */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0;
    border-bottom: 1px solid {COLOR_BORDER};
}}
.stTabs [data-baseweb="tab"] {{
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 500 !important;
    color: {COLOR_INK_MUTED} !important;
    padding: 10px 16px !important;
}}
.stTabs [data-baseweb="tab"][aria-selected="true"] {{
    color: {COLOR_INK} !important;
    border-bottom: 2px solid {COLOR_INK} !important;
}}

/* metric */
[data-testid="stMetric"] {{
    background: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 16px 20px;
}}
[data-testid="stMetricLabel"] {{
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
    color: {COLOR_INK_MUTED} !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
[data-testid="stMetricValue"] {{
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 600 !important;
    color: {COLOR_INK} !important;
    font-size: 28px !important;
}}
</style>
"""

_CSS_SECTION = f"""
<style>
.section-header {{ margin: 32px 0 16px 0; }}
.section__eyebrow {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: {COLOR_INK_MUTED};
    letter-spacing: 0.05em;
    margin-bottom: 4px;
    text-transform: lowercase;
}}
.section__title {{
    font-size: 22px;
    font-weight: 600;
    color: {COLOR_INK};
    margin: 0;
    letter-spacing: -0.01em;
}}
</style>
"""

_CSS_STAT = f"""
<style>
.stat-card {{
    background: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 16px 18px;
    height: 100%;
    transition: border-color 0.15s ease;
}}
.stat-card:hover {{ border-color: {COLOR_PRIMARY}; }}
.stat__label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: {COLOR_INK_MUTED};
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
}}
.stat__value {{
    font-size: 26px;
    font-weight: 600;
    color: {COLOR_INK};
    line-height: 1.1;
    letter-spacing: -0.02em;
}}
.stat__hint {{
    font-size: 11px;
    color: {COLOR_INK_MUTED};
    margin-top: 4px;
}}
</style>
"""


# ─── Plotly 主题配置 ───
def plotly_layout_defaults() -> dict:
    """统一 Plotly 图表外观,在 fig.update_layout(**plotly_layout_defaults()) 中传入"""
    return dict(
        font=dict(family="IBM Plex Sans, sans-serif", color=COLOR_INK, size=12),
        plot_bgcolor=COLOR_SURFACE,
        paper_bgcolor=COLOR_SURFACE,
        margin=dict(t=40, l=40, r=20, b=40),
        colorway=[
            COLOR_INK, COLOR_PRIMARY, COLOR_ACCENT, COLOR_SUCCESS,
            COLOR_WARN, "#7B5CE0", "#FF8A6B", "#3FB58E",
        ],
        xaxis=dict(gridcolor=COLOR_BORDER, linecolor=COLOR_BORDER, tickfont=dict(size=11)),
        yaxis=dict(gridcolor=COLOR_BORDER, linecolor=COLOR_BORDER, tickfont=dict(size=11)),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=COLOR_BORDER, borderwidth=1),
    )

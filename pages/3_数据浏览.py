"""数据浏览页:按类别展示已采集数据,带筛选 + SQL 透出。"""
import streamlit as st
import pandas as pd
from sqlalchemy import text

from database import init_db
from db.connection import get_engine
from ui_theme import apply_theme, page_header

apply_theme(page_title="数据浏览 · AI-Scraper", page_icon="▣")
init_db()

page_header(
    eyebrow="data / explore",
    title="数据浏览",
    subtitle="按类别浏览 MySQL 中的结构化数据。每个 tab 底部展开可查看实际 SQL。",
    active_stage="explore",
)

engine = get_engine()


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def render_table(df: pd.DataFrame, image_cols: list[str] | None = None,
                 link_cols: list[str] | None = None, height: int = 420):
    """渲染数据表 — 自动把图片列展示为缩略图,链接列展示为可点击链接。"""
    config = {}
    for col in image_cols or []:
        if col in df.columns:
            config[col] = st.column_config.ImageColumn(
                label=col, width="small", help="点击打开原图"
            )
    for col in link_cols or []:
        if col in df.columns:
            config[col] = st.column_config.LinkColumn(label=col, width="small")
    st.dataframe(df, width="stretch", height=height, column_config=config)


def show_sql(sql: str, params: dict | None = None):
    """在 expander 里展示真实跑的 SQL"""
    with st.expander("🔍 查看本页 SQL"):
        full = sql
        if params:
            for k, v in params.items():
                placeholder = f":{k}"
                full = full.replace(placeholder, repr(v))
        st.code(full.strip(), language="sql")


tabs = st.tabs(["📚 图书", "💬 名言", "🛒 商品", "📰 新闻", "💼 招聘", "📦 通用"])

# ============ 图书 ============
with tabs[0]:
    c1, c2, c3 = st.columns([3, 1, 1])
    kw = c1.text_input("搜索 (标题 / 作者)", key="bk_kw").strip()
    rate_min = c2.number_input("最低评分", 0, 5, 0, key="bk_rate")
    limit = c3.number_input("条数", 10, 1000, 100, key="bk_lim")

    sql = """
        SELECT b.cover_image_url AS 封面,
               b.id, b.title,
               a.name AS author,
               a.nationality,
               b.price, b.currency, b.rating, b.availability,
               b.scraped_at
        FROM books b
        LEFT JOIN authors a ON b.author_id = a.id
        WHERE 1=1
        {kw_filter}
        AND COALESCE(b.rating, 0) >= :rate_min
        ORDER BY b.scraped_at DESC
        LIMIT :lim
    """.replace(
        "{kw_filter}",
        "AND (b.title LIKE :kw OR a.name LIKE :kw)" if kw else ""
    )
    params = {"rate_min": rate_min, "lim": int(limit)}
    if kw:
        params["kw"] = f"%{kw}%"
    df = run_query(sql, params)
    render_table(df, image_cols=["封面"])
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 名言 ============
with tabs[1]:
    c1, c2 = st.columns([3, 1])
    kw = c1.text_input("搜索 (内容 / 作者)", key="qt_kw").strip()
    limit = c2.number_input("条数", 10, 1000, 100, key="qt_lim")

    sql = """
        SELECT q.id,
               LEFT(q.quote, 200) AS quote,
               a.name AS author,
               GROUP_CONCAT(t.name SEPARATOR ', ') AS tags,
               q.scraped_at
        FROM quotes q
        LEFT JOIN authors a ON q.author_id = a.id
        LEFT JOIN quote_tags qt ON q.id = qt.quote_id
        LEFT JOIN tags t ON qt.tag_id = t.id
        WHERE 1=1
        {kw_filter}
        GROUP BY q.id, q.quote, a.name, q.scraped_at
        ORDER BY q.scraped_at DESC
        LIMIT :lim
    """.replace(
        "{kw_filter}",
        "AND (q.quote LIKE :kw OR a.name LIKE :kw)" if kw else ""
    )
    params = {"lim": int(limit)}
    if kw:
        params["kw"] = f"%{kw}%"
    df = run_query(sql, params)
    st.dataframe(df, width="stretch", height=420)
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 商品 ============
with tabs[2]:
    c1, c2 = st.columns([3, 1])
    kw = c1.text_input("搜索 (商品 / 品牌)", key="pd_kw").strip()
    limit = c2.number_input("条数", 10, 1000, 100, key="pd_lim")

    sql = """
        SELECT p.image_url AS 商品图,
               p.id, p.name,
               br.name AS brand,
               p.price, p.currency, p.rating, p.sku,
               p.scraped_at
        FROM products p
        LEFT JOIN brands br ON p.brand_id = br.id
        WHERE 1=1
        {kw_filter}
        ORDER BY p.scraped_at DESC
        LIMIT :lim
    """.replace(
        "{kw_filter}",
        "AND (p.name LIKE :kw OR br.name LIKE :kw)" if kw else ""
    )
    params = {"lim": int(limit)}
    if kw:
        params["kw"] = f"%{kw}%"
    df = run_query(sql, params)
    render_table(df, image_cols=["商品图"])
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 新闻 ============
with tabs[3]:
    c1, c2 = st.columns([3, 1])
    kw = c1.text_input("搜索 (标题 / 摘要)", key="nw_kw").strip()
    limit = c2.number_input("条数", 10, 1000, 100, key="nw_lim")

    sql = """
        SELECT n.cover_image_url AS 头图,
               n.id, n.title,
               n.author,
               s.name AS source,
               n.publish_date,
               LEFT(n.summary, 120) AS summary,
               n.scraped_at
        FROM news n
        LEFT JOIN news_sources s ON n.source_id = s.id
        WHERE 1=1
        {kw_filter}
        ORDER BY n.scraped_at DESC
        LIMIT :lim
    """.replace(
        "{kw_filter}",
        "AND (n.title LIKE :kw OR n.summary LIKE :kw)" if kw else ""
    )
    params = {"lim": int(limit)}
    if kw:
        params["kw"] = f"%{kw}%"
    df = run_query(sql, params)
    render_table(df, image_cols=["头图"])
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 招聘 ============
with tabs[4]:
    c1, c2 = st.columns([3, 1])
    kw = c1.text_input("搜索 (职位 / 公司)", key="jb_kw").strip()
    limit = c2.number_input("条数", 10, 1000, 100, key="jb_lim")

    sql = """
        SELECT id, job_title, company, location, salary, post_date, scraped_at
        FROM jobs_listings
        WHERE 1=1
        {kw_filter}
        ORDER BY scraped_at DESC
        LIMIT :lim
    """.replace(
        "{kw_filter}",
        "AND (job_title LIKE :kw OR company LIKE :kw)" if kw else ""
    )
    params = {"lim": int(limit)}
    if kw:
        params["kw"] = f"%{kw}%"
    df = run_query(sql, params)
    st.dataframe(df, width="stretch", height=420)
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 通用 ============
with tabs[5]:
    cats = run_query("SELECT DISTINCT category FROM generic_items ORDER BY category")
    cat_options = ["(全部)"] + cats["category"].tolist()

    c1, c2 = st.columns([2, 1])
    chosen = c1.selectbox("类别", cat_options, key="gn_cat")
    limit = c2.number_input("条数", 10, 1000, 100, key="gn_lim")

    sql = """
        SELECT id, category, data_json, source_url, scraped_at
        FROM generic_items
        WHERE 1=1
        {cat_filter}
        ORDER BY scraped_at DESC
        LIMIT :lim
    """.replace(
        "{cat_filter}",
        "AND category = :cat" if chosen != "(全部)" else ""
    )
    params = {"lim": int(limit)}
    if chosen != "(全部)":
        params["cat"] = chosen
    df = run_query(sql, params)
    st.dataframe(df, width="stretch", height=420)
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

"""数据浏览页:按类别展示已采集数据,带筛选 + SQL 透出。"""
import streamlit as st
import pandas as pd
from sqlalchemy import text

from database import init_db
from db.connection import get_engine

init_db()

st.set_page_config(page_title="数据浏览", page_icon="📂", layout="wide")
st.markdown("""
<style>
    [data-testid="stToolbar"] {display: none !important;}
    .stDeployButton {display: none !important;}
    #MainMenu {display: none !important;}
    header {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("### 📂 数据浏览")
st.caption("按类别浏览已采集到 MySQL 的结构化数据。每个 tab 底部展示对应 SQL。")
st.markdown("---")

engine = get_engine()


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


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
        SELECT b.id, b.title,
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
    st.dataframe(df, width="stretch", height=420)
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
        SELECT p.id, p.name,
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
    st.dataframe(df, width="stretch", height=420)
    st.caption(f"共 {len(df)} 行")
    show_sql(sql, params)

# ============ 新闻 ============
with tabs[3]:
    c1, c2 = st.columns([3, 1])
    kw = c1.text_input("搜索 (标题 / 摘要)", key="nw_kw").strip()
    limit = c2.number_input("条数", 10, 1000, 100, key="nw_lim")

    sql = """
        SELECT n.id, n.title,
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
    st.dataframe(df, width="stretch", height=420)
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

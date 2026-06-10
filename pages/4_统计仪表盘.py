"""统计仪表盘:6 个图表 + 每个图表对应的 SQL 透出。
展示 GROUP BY / JOIN / HAVING / DATE 函数 / 触发器表 等数据库技巧。"""
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text

from database import init_db
from db.connection import get_engine

init_db()
engine = get_engine()

st.set_page_config(page_title="统计仪表盘", page_icon="📊", layout="wide")
st.markdown("""
<style>
    [data-testid="stToolbar"] {display: none !important;}
    .stDeployButton {display: none !important;}
    #MainMenu {display: none !important;}
    header {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("### 📊 统计仪表盘")
st.caption("基于 MySQL 视图 + 聚合查询的可视化统计。每张图配对应 SQL。")
st.markdown("---")


def query(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def chart_with_sql(title: str, sql: str, render_fn):
    """统一渲染:标题 + 图表 + SQL expander"""
    st.subheader(title)
    df = query(sql)
    if df.empty:
        st.info("暂无数据")
    else:
        render_fn(df)
    with st.expander("🔍 查看 SQL"):
        st.code(sql.strip(), language="sql")
    st.markdown("---")


# ============ KPI 概览 ============
kpi_sql = """
    SELECT
        (SELECT COUNT(*) FROM jobs WHERE status='completed') AS completed_jobs,
        (SELECT COUNT(*) FROM books)         AS books,
        (SELECT COUNT(*) FROM quotes)        AS quotes,
        (SELECT COUNT(*) FROM products)      AS products,
        (SELECT COUNT(*) FROM news)          AS news,
        (SELECT COUNT(*) FROM authors)       AS authors,
        (SELECT COUNT(*) FROM generic_items) AS generic
"""
kpi = query(kpi_sql).iloc[0]
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
c1.metric("已完成任务", int(kpi["completed_jobs"]))
c2.metric("📚 图书", int(kpi["books"]))
c3.metric("💬 名言", int(kpi["quotes"]))
c4.metric("🛒 商品", int(kpi["products"]))
c5.metric("📰 新闻", int(kpi["news"]))
c6.metric("✍️ 作者", int(kpi["authors"]))
c7.metric("📦 通用", int(kpi["generic"]))
with st.expander("🔍 KPI SQL"):
    st.code(kpi_sql.strip(), language="sql")
st.markdown("---")


# ============ 图 1: 各类别数据量分布 (使用视图 + JOIN) ============
def render_category_pie(df: pd.DataFrame):
    fig = px.pie(df, values="total_rows", names="name_zh", hole=0.4,
                 title="各类别数据行数占比")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "1. 各类别数据量分布 (来自视图 v_category_stats)",
    """
    SELECT name_zh, total_rows
    FROM v_category_stats
    WHERE total_rows > 0
    ORDER BY total_rows DESC
    """,
    render_category_pie,
)


# ============ 图 2: 名言作者 Top 10 (3 表 JOIN + GROUP BY + HAVING + LIMIT) ============
def render_top_authors(df: pd.DataFrame):
    fig = px.bar(df, x="quote_count", y="name", orientation="h",
                 title="按名言数量排名前 10 的作者", text="quote_count")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "2. 名言作者 Top 10 (JOIN + GROUP BY + HAVING)",
    """
    SELECT a.name,
           COUNT(q.id) AS quote_count
    FROM authors a
    JOIN quotes q ON a.id = q.author_id
    GROUP BY a.id, a.name
    HAVING quote_count >= 1
    ORDER BY quote_count DESC
    LIMIT 10
    """,
    render_top_authors,
)


# ============ 图 3: 图书评分分布 (GROUP BY) ============
def render_book_rating(df: pd.DataFrame):
    fig = px.bar(df, x="rating", y="cnt", title="图书评分分布", text="cnt")
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "3. 图书评分分布 (GROUP BY)",
    """
    SELECT rating, COUNT(*) AS cnt
    FROM books
    WHERE rating IS NOT NULL
    GROUP BY rating
    ORDER BY rating
    """,
    render_book_rating,
)


# ============ 图 4: 图书价格区间分布 (FLOOR + GROUP BY) ============
def render_price_buckets(df: pd.DataFrame):
    fig = px.bar(df, x="bucket", y="cnt", title="图书价格分布(每 10 元一档)", text="cnt")
    fig.update_xaxes(type="category")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "4. 图书价格区间分布 (子查询 + FLOOR + GROUP BY)",
    """
    SELECT
        CONCAT(bin * 10, '-', bin * 10 + 10) AS bucket,
        COUNT(*) AS cnt
    FROM (
        SELECT FLOOR(price / 10) AS bin
        FROM books
        WHERE price IS NOT NULL
    ) AS t
    GROUP BY bin
    ORDER BY bin
    """,
    render_price_buckets,
)


# ============ 图 5: 每日采集量趋势 (DATE 函数) ============
def render_daily(df: pd.DataFrame):
    fig = px.line(df, x="day", y="cnt", markers=True, title="每日采集行数趋势")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "5. 每日采集量趋势 (DATE + GROUP BY 日期)",
    """
    SELECT DATE(scraped_at) AS day, COUNT(*) AS cnt FROM (
        SELECT scraped_at FROM books
        UNION ALL SELECT scraped_at FROM quotes
        UNION ALL SELECT scraped_at FROM products
        UNION ALL SELECT scraped_at FROM news
        UNION ALL SELECT scraped_at FROM jobs_listings
        UNION ALL SELECT scraped_at FROM generic_items
    ) AS u
    GROUP BY day
    ORDER BY day
    """,
    render_daily,
)


# ============ 图 6: 价格变更历史 (来自触发器自动生成的 price_history) ============
def render_price_history(df: pd.DataFrame):
    if df.empty:
        st.info("尚无价格变更记录。当 books / products 表的 price 字段被更新时,触发器会自动写入此表。")
        return
    fig = px.line(df, x="changed_at", y="new_price", color="entity",
                  markers=True, title="历史价格变化(由触发器自动维护)")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "6. 价格变更历史 (展示触发器效果)",
    """
    SELECT
        ph.changed_at,
        ph.old_price, ph.new_price,
        CASE
            WHEN ph.book_id IS NOT NULL THEN CONCAT('book#', b.title)
            WHEN ph.product_id IS NOT NULL THEN CONCAT('product#', p.name)
        END AS entity
    FROM price_history ph
    LEFT JOIN books b ON ph.book_id = b.id
    LEFT JOIN products p ON ph.product_id = p.id
    ORDER BY ph.changed_at DESC
    LIMIT 50
    """,
    render_price_history,
)

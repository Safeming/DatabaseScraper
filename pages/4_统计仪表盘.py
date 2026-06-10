"""统计仪表盘:6 个图表 + 每个图表对应的 SQL 透出。
展示 GROUP BY / JOIN / HAVING / DATE 函数 / 触发器表 等数据库技巧。"""
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text

from database import init_db
from db.connection import get_engine
from ui_theme import apply_theme, page_header, section, stat_card, plotly_layout_defaults

apply_theme(page_title="统计仪表盘 · AI-Scraper", page_icon="▣")
init_db()
engine = get_engine()

page_header(
    eyebrow="data / analyze",
    title="统计仪表盘",
    subtitle="基于 MySQL 视图与聚合查询的可视化分析。每张图下方展开可查看实际 SQL。",
    active_stage="analyze",
)


def query(sql: str) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


def chart_with_sql(title: str, sql: str, render_fn, eyebrow: str = ""):
    """统一渲染:标题 + 图表 + SQL expander"""
    section(title, eyebrow=eyebrow)
    df = query(sql)
    if df.empty:
        st.info("暂无数据 — 提交一些采集任务后这里会出现统计")
    else:
        render_fn(df)
    with st.expander("查看 SQL"):
        st.code(sql.strip(), language="sql")


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
section("数据库概览", eyebrow="SELECT COUNT(*) ...")
c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
with c1: stat_card("任务完成数", int(kpi["completed_jobs"]))
with c2: stat_card("图书", int(kpi["books"]))
with c3: stat_card("名言", int(kpi["quotes"]))
with c4: stat_card("商品", int(kpi["products"]))
with c5: stat_card("新闻", int(kpi["news"]))
with c6: stat_card("作者", int(kpi["authors"]))
with c7: stat_card("通用", int(kpi["generic"]))
with st.expander("查看 KPI SQL"):
    st.code(kpi_sql.strip(), language="sql")


# ============ 图 1: 各类别数据量分布 (使用视图 + JOIN) ============
def render_category_pie(df: pd.DataFrame):
    fig = px.pie(df, values="total_rows", names="name_zh", hole=0.55)
    fig.update_traces(textposition="outside", textinfo="label+percent")
    fig.update_layout(**plotly_layout_defaults(), showlegend=False)
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "各类别数据量分布",
    """
    SELECT name_zh, total_rows
    FROM v_category_stats
    WHERE total_rows > 0
    ORDER BY total_rows DESC
    """,
    render_category_pie,
    eyebrow="01 · view v_category_stats",
)


# ============ 图 2: 名言作者 Top 10 (3 表 JOIN + GROUP BY + HAVING + LIMIT) ============
def render_top_authors(df: pd.DataFrame):
    fig = px.bar(df, x="quote_count", y="name", orientation="h", text="quote_count")
    fig.update_traces(textposition="outside")
    fig.update_layout(**plotly_layout_defaults())
    fig.update_yaxes(categoryorder="total ascending", title="")
    fig.update_xaxes(title="名言数")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "高产作者 Top 10",
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
    eyebrow="02 · join · group by · having",
)


# ============ 图 3: 图书评分分布 (GROUP BY) ============
def render_book_rating(df: pd.DataFrame):
    fig = px.bar(df, x="rating", y="cnt", text="cnt")
    fig.update_traces(textposition="outside")
    fig.update_layout(**plotly_layout_defaults())
    fig.update_xaxes(type="category", title="评分(★)")
    fig.update_yaxes(title="数量")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "图书评分分布",
    """
    SELECT rating, COUNT(*) AS cnt
    FROM books
    WHERE rating IS NOT NULL
    GROUP BY rating
    ORDER BY rating
    """,
    render_book_rating,
    eyebrow="03 · group by rating",
)


# ============ 图 4: 图书价格区间分布 (FLOOR + GROUP BY) ============
def render_price_buckets(df: pd.DataFrame):
    fig = px.bar(df, x="bucket", y="cnt", text="cnt")
    fig.update_traces(textposition="outside")
    fig.update_layout(**plotly_layout_defaults())
    fig.update_xaxes(type="category", title="价格区间")
    fig.update_yaxes(title="图书数")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "图书价格分布",
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
    eyebrow="04 · subquery · floor · group by",
)


# ============ 图 5: 每日采集量趋势 (DATE 函数) ============
def render_daily(df: pd.DataFrame):
    fig = px.area(df, x="day", y="cnt", markers=True)
    fig.update_traces(line_color="#4F2DD8", fillcolor="rgba(79, 45, 216, 0.12)")
    fig.update_layout(**plotly_layout_defaults())
    fig.update_xaxes(title="日期")
    fig.update_yaxes(title="采集行数")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "每日采集量趋势",
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
    eyebrow="05 · union all · date()",
)


# ============ 图 6: 价格变更历史 (来自触发器自动生成的 price_history) ============
def render_price_history(df: pd.DataFrame):
    if df.empty:
        st.info("尚无价格变更记录。当 books / products 表的 price 字段被更新时,触发器会自动写入此表。")
        return
    fig = px.line(df, x="changed_at", y="new_price", color="entity", markers=True)
    fig.update_layout(**plotly_layout_defaults())
    fig.update_xaxes(title="时间")
    fig.update_yaxes(title="价格")
    st.plotly_chart(fig, width="stretch")

chart_with_sql(
    "价格变更历史(触发器产物)",
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
    eyebrow="06 · trigger output · case when",
)

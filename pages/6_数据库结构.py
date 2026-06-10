"""数据库结构展示:从 information_schema 动态读取表/列/索引/外键/触发器/视图。
答辩时直接展示数据库设计的全貌。"""
import streamlit as st
import pandas as pd
from sqlalchemy import text

from database import init_db
from db.connection import get_engine
from ui_theme import apply_theme, page_header

apply_theme(page_title="数据库结构 · AI-Scraper", page_icon="▣")
init_db()
engine = get_engine()

page_header(
    eyebrow="meta / schema",
    title="数据库结构",
    subtitle="从 information_schema 实时读取的表 / 列 / 索引 / 外键 / 触发器 / 视图元数据。",
    active_stage="store",
)

# ─── ER 图 ───
import os
_ER_IMG = os.path.join(os.path.dirname(__file__), "..", "doc", "ER图.png")
if os.path.isfile(_ER_IMG):
    st.subheader("🗺️ ER 图")
    st.image(_ER_IMG, caption="数据库实体关系图", width="stretch")
    st.markdown("---")
else:
    with st.expander("🗺️ ER 图(尚未导出)"):
        st.info(
            "尚未生成 ER 图 PNG。可用 [dbdiagram.io](https://dbdiagram.io/d) 在线编辑器:"
            "把 `doc/ER图.dbml` 复制进去,自动生成图后导出 PNG,命名为 `doc/ER图.png` 即可在此处显示。"
        )
    st.markdown("---")

DB_NAME = "ai_scraper_db"


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params or {})
        # MySQL information_schema 在某些版本返回大写列名,统一转小写
        df.columns = [c.lower() for c in df.columns]
        return df


# ─── 概览 ───
st.subheader("📋 表概览")
tables_df = query("""
    SELECT table_name, table_rows, engine, table_collation, table_comment
    FROM information_schema.tables
    WHERE table_schema = :db AND table_type = 'BASE TABLE'
    ORDER BY table_name
""", {"db": DB_NAME})
tables_df.columns = ["表名", "行数(估)", "引擎", "字符集", "注释"]
st.dataframe(tables_df, width="stretch", height=460)

st.markdown("---")

# ─── 视图 ───
st.subheader("👁️ 视图")
views_df = query("""
    SELECT table_name, view_definition
    FROM information_schema.views
    WHERE table_schema = :db
    ORDER BY table_name
""", {"db": DB_NAME})
if views_df.empty:
    st.info("无视图")
else:
    for _, row in views_df.iterrows():
        with st.expander(f"📐 {row['table_name']}"):
            st.code(row["view_definition"], language="sql")

st.markdown("---")

# ─── 触发器 ───
st.subheader("⚡ 触发器")
trigs_df = query("""
    SELECT trigger_name, event_object_table AS table_name,
           action_timing, event_manipulation, action_statement
    FROM information_schema.triggers
    WHERE trigger_schema = :db
""", {"db": DB_NAME})
if trigs_df.empty:
    st.info("无触发器")
else:
    for _, row in trigs_df.iterrows():
        with st.expander(
            f"⚡ {row['trigger_name']}  "
            f"({row['action_timing']} {row['event_manipulation']} ON {row['table_name']})"
        ):
            st.code(row["action_statement"], language="sql")

st.markdown("---")

# ─── 单表细节 ───
st.subheader("🔍 单表详情")
table_choice = st.selectbox(
    "选择表",
    tables_df["表名"].tolist(),
    index=tables_df["表名"].tolist().index("books") if "books" in tables_df["表名"].tolist() else 0
)

# 列
cols_df = query("""
    SELECT column_name, column_type, is_nullable, column_key, column_default,
           extra, column_comment
    FROM information_schema.columns
    WHERE table_schema = :db AND table_name = :tbl
    ORDER BY ordinal_position
""", {"db": DB_NAME, "tbl": table_choice})
cols_df.columns = ["列名", "类型", "可空", "键", "默认值", "Extra", "注释"]
st.markdown("**列定义**")
st.dataframe(cols_df, width="stretch")

# 索引
idx_df = query("""
    SELECT index_name, non_unique, column_name, seq_in_index, index_type
    FROM information_schema.statistics
    WHERE table_schema = :db AND table_name = :tbl
    ORDER BY index_name, seq_in_index
""", {"db": DB_NAME, "tbl": table_choice})
idx_df.columns = ["索引名", "可重复", "列", "顺序", "类型"]
st.markdown("**索引**")
st.dataframe(idx_df, width="stretch")

# 外键
fk_df = query("""
    SELECT constraint_name, column_name,
           referenced_table_name, referenced_column_name
    FROM information_schema.key_column_usage
    WHERE table_schema = :db AND table_name = :tbl
      AND referenced_table_name IS NOT NULL
""", {"db": DB_NAME, "tbl": table_choice})
fk_df.columns = ["约束名", "本列", "引用表", "引用列"]
st.markdown("**外键**")
if fk_df.empty:
    st.caption("(无外键)")
else:
    st.dataframe(fk_df, width="stretch")

# 检查约束(MySQL 8.0+)
ck_df = query("""
    SELECT cc.constraint_name, cc.check_clause
    FROM information_schema.check_constraints cc
    JOIN information_schema.table_constraints tc
      ON cc.constraint_name = tc.constraint_name
    WHERE tc.table_schema = :db AND tc.table_name = :tbl
""", {"db": DB_NAME, "tbl": table_choice})
ck_df.columns = ["约束名", "检查条件"]
st.markdown("**CHECK 约束**")
if ck_df.empty:
    st.caption("(无 CHECK 约束)")
else:
    st.dataframe(ck_df, width="stretch")

st.markdown("---")
with st.expander("📝 数据库设计要点"):
    st.markdown("""
**范式化设计:**
- 维表(authors / brands / news_sources / tags)拆分,业务表通过外键引用
- 多对多关系(quote_tags)用关联表实现

**约束:**
- 主键 / 唯一键(同书同作者只能有一条)
- 外键 + ON DELETE 行为(SET NULL / CASCADE)
- CHECK 约束(price >= 0, rating BETWEEN 1 AND 5)
- 生成列(news.url_hash 用 SHA2 计算 URL 哈希做唯一索引)

**索引:**
- 普通 B+树索引(scraped_at / price / rating)
- 复合索引(brand_id + price)
- 全文索引(books.title / quotes.quote / news.title+summary)

**视图:**
- v_book_summary / v_top_authors / v_category_stats / v_product_summary

**触发器:**
- trg_book_price_change / trg_product_price_change 自动维护 price_history
""")

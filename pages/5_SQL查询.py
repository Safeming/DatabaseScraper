"""SQL 查询器 - 用只读账号执行 SELECT,带预设示例 + EXPLAIN。"""
import time
import re
import streamlit as st
import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import init_db
from db.connection import get_readonly_engine

init_db()

st.set_page_config(page_title="SQL 查询器", page_icon="🔍", layout="wide")
st.markdown("""
<style>
    [data-testid="stToolbar"] {display: none !important;}
    .stDeployButton {display: none !important;}
    #MainMenu {display: none !important;}
    header {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("### 🔍 SQL 查询器")
st.caption("使用只读账号执行 SQL,演示 JOIN / 子查询 / GROUP BY / 窗口函数等技巧。")
st.markdown("---")


# ─── 安全检查:只允许 SELECT / SHOW / DESCRIBE / EXPLAIN ───
ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH")
DANGEROUS_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|REPLACE|CALL|LOAD|HANDLER)\b",
    re.IGNORECASE
)


def is_safe_query(sql: str) -> tuple[bool, str]:
    """白名单检查 + 关键字黑名单"""
    s = sql.strip().rstrip(";").strip()
    if not s:
        return False, "查询不能为空"

    # 取第一个单词
    first = s.split(None, 1)[0].upper()
    if first not in ALLOWED_PREFIXES:
        return False, f"只允许 SELECT/SHOW/DESC/EXPLAIN/WITH 开头,当前是 {first!r}"

    # 黑名单
    m = DANGEROUS_KEYWORDS.search(s)
    if m:
        return False, f"检测到危险关键字: {m.group(0)}"

    # 禁止多语句(防 SQL 注入式 ;DROP)
    inner = re.sub(r"'[^']*'|\"[^\"]*\"", "", s)
    if ";" in inner:
        return False, "禁止多语句(分号分隔)"

    return True, "OK"


# ─── 预设示例(覆盖课程关键技巧) ───
PRESET_QUERIES = {
    "(选择一个示例…)": "",

    "JOIN: 名言 + 作者": """SELECT q.id, LEFT(q.quote, 80) AS quote_excerpt, a.name AS author
FROM quotes q
JOIN authors a ON q.author_id = a.id
ORDER BY q.id DESC
LIMIT 20;""",

    "三表 JOIN: 作者 - 名言数 - 标签数": """SELECT a.name AS author,
       COUNT(DISTINCT q.id) AS quote_count,
       COUNT(DISTINCT qt.tag_id) AS tag_count
FROM authors a
JOIN quotes q ON a.id = q.author_id
LEFT JOIN quote_tags qt ON q.id = qt.quote_id
GROUP BY a.id, a.name
ORDER BY quote_count DESC
LIMIT 15;""",

    "子查询: 高于平均价的图书": """SELECT title, price
FROM books
WHERE price > (SELECT AVG(price) FROM books WHERE price IS NOT NULL)
ORDER BY price DESC
LIMIT 20;""",

    "GROUP BY + HAVING: 拥有 ≥2 本书的作者": """SELECT a.name, COUNT(*) AS book_count, AVG(b.price) AS avg_price
FROM authors a
JOIN books b ON a.id = b.author_id
GROUP BY a.id, a.name
HAVING COUNT(*) >= 2
ORDER BY book_count DESC;""",

    "窗口函数: 各品牌价格排名": """SELECT name, brand_id, price,
       RANK() OVER (PARTITION BY brand_id ORDER BY price DESC) AS rank_in_brand
FROM products
WHERE price IS NOT NULL
ORDER BY brand_id, rank_in_brand
LIMIT 30;""",

    "全文索引: 在名言中搜 'love'": """SELECT id, LEFT(quote, 100) AS excerpt
FROM quotes
WHERE MATCH(quote) AGAINST('love' IN NATURAL LANGUAGE MODE)
LIMIT 20;""",

    "视图: 各类别统计": """SELECT * FROM v_category_stats ORDER BY total_rows DESC;""",

    "视图: 高产作者": """SELECT * FROM v_top_authors ORDER BY book_count DESC LIMIT 20;""",

    "EXPLAIN: 看执行计划 (是否走索引)": """EXPLAIN
SELECT q.quote, a.name FROM quotes q
JOIN authors a ON q.author_id = a.id
WHERE a.name = 'Albert Einstein';""",

    "DESCRIBE: 看表结构": """DESCRIBE quotes;""",

    "SHOW INDEXES: 看索引信息": """SHOW INDEXES FROM books;""",
}


col_left, col_right = st.columns([2, 1])
with col_right:
    preset = st.selectbox("预设示例", list(PRESET_QUERIES.keys()), key="preset")
    sample = PRESET_QUERIES[preset]

# 把示例填入文本框
if "sql_text" not in st.session_state:
    st.session_state.sql_text = ""
if sample and st.session_state.get("last_preset") != preset:
    st.session_state.sql_text = sample
    st.session_state.last_preset = preset

with col_left:
    sql_input = st.text_area(
        "SQL (只读)",
        value=st.session_state.sql_text,
        height=200,
        key="sql_text",
    )

c1, c2, c3 = st.columns([1, 1, 4])
run_btn = c1.button("▶ 执行", width="stretch")
explain_btn = c2.button("🧠 EXPLAIN", width="stretch")

if run_btn or explain_btn:
    sql = sql_input.strip().rstrip(";")

    if explain_btn and not sql.upper().startswith("EXPLAIN"):
        sql = f"EXPLAIN {sql}"

    safe, reason = is_safe_query(sql)
    if not safe:
        st.error(f"❌ 查询被拒绝: {reason}")
    else:
        try:
            engine = get_readonly_engine()
            t0 = time.time()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
                    elapsed = time.time() - t0
                    st.success(f"✅ 返回 {len(df)} 行 / 耗时 {elapsed*1000:.1f} ms")
                    st.dataframe(df, width="stretch", height=420)
                else:
                    st.info("查询执行成功(无结果集)。")
        except SQLAlchemyError as e:
            st.error(f"SQL 错误: {e}")
        except Exception as e:
            st.error(f"执行异常: {e}")

with st.expander("ℹ️ 关于安全限制"):
    st.markdown("""
- **只读账号**:本页查询使用 `ai_scraper_ro` MySQL 用户,仅授予 `SELECT, SHOW VIEW` 权限
- **白名单**:必须以 `SELECT / SHOW / DESCRIBE / EXPLAIN / WITH` 开头
- **黑名单**:禁止 `INSERT / UPDATE / DELETE / DROP / TRUNCATE / ALTER / CREATE / GRANT / REVOKE` 等
- **禁多语句**:不允许通过分号拼接多条语句
- 即使绕过应用层,数据库层的权限授予也会兜底
    """)

"""按类别路由的入库 store。

每个 store 函数:
  store_xxx(session: Session, job_id: int, rows: list[dict]) -> int
返回成功插入的行数。

调用方:db/repository.py:store_extracted_rows() 根据 category 选 store。
"""
from __future__ import annotations

import logging
from typing import Callable

from .books import store_books
from .products import store_products
from .quotes import store_quotes
from .news import store_news
from .jobs_listings import store_jobs_listings
from .generic import store_generic

logger = logging.getLogger(__name__)

# 路由表: category code -> store 函数
STORE_REGISTRY: dict[str, Callable] = {
    "books": store_books,
    "products": store_products,
    "quotes": store_quotes,
    "news": store_news,
    "jobs": store_jobs_listings,
}


def store_by_category(session, job_id: int, rows: list[dict],
                      category: str | None) -> int:
    """根据类别路由到专属 store;无匹配时走 generic_items。"""
    if not rows:
        return 0
    cat = (category or "general").lower()
    store_fn = STORE_REGISTRY.get(cat)
    if store_fn is not None:
        try:
            return store_fn(session, job_id, rows)
        except Exception as e:
            logger.error(f"Specialized store '{cat}' failed: {e}, falling back to generic")
            session.rollback()
    return store_generic(session, job_id, cat, rows)

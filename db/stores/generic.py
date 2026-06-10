"""通用 fallback 入库:把整行 JSON 塞到 generic_items 表。
用于 books/products/quotes/news/jobs 之外的所有类别(movies/papers/forum/...)。
"""
from __future__ import annotations

import json
import logging

from db.models import GenericItem

logger = logging.getLogger(__name__)


def store_generic(session, job_id: int, category: str, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        if not row:
            continue
        try:
            source_url = row.get("url") or row.get("source_url")
            item = GenericItem(
                job_id=job_id,
                category=category,
                data_json=row,
                source_url=str(source_url)[:2048] if source_url else None,
            )
            session.add(item)
            inserted += 1
        except Exception as e:
            logger.warning(f"Generic insert failed: {e}")
    if inserted:
        session.flush()
    return inserted

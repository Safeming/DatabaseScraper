"""图书入库:books + authors(维表 upsert) + 触发 price_history。"""
from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from db.models import Book, Author
from db.value_parsers import parse_price, parse_rating, coerce_str

logger = logging.getLogger(__name__)


def _upsert_author(session, name: str | None) -> int | None:
    name = coerce_str(name, max_len=200)
    if not name:
        return None
    existing = session.execute(
        select(Author).where(Author.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing.id
    author = Author(name=name)
    session.add(author)
    session.flush()
    return author.id


def store_books(session, job_id: int, rows: list[dict]) -> int:
    """书目入库:upsert author,然后 INSERT ... ON DUPLICATE KEY UPDATE 到 books。
    重复书(同 title + author)时更新 price → 触发 price_history 触发器。
    """
    inserted = 0
    for row in rows:
        title = coerce_str(row.get("title"), max_len=500)
        if not title:
            continue

        author_id = _upsert_author(session, row.get("author"))
        price, currency = parse_price(row.get("price"))
        rating_raw = parse_rating(row.get("rating"))
        rating = int(round(rating_raw)) if rating_raw is not None else None
        if rating is not None:
            rating = max(1, min(5, rating))
        availability = coerce_str(row.get("availability"), max_len=50)
        isbn = coerce_str(row.get("isbn"), max_len=20)
        source_url = coerce_str(row.get("url") or row.get("source_url"), max_len=2048)

        stmt = mysql_insert(Book).values(
            job_id=job_id,
            title=title,
            author_id=author_id,
            price=price,
            currency=currency or "GBP",
            rating=rating,
            availability=availability,
            isbn=isbn,
            source_url=source_url,
        )
        # 重复时更新价格 / 评分 / 库存(自动触发 price_history)
        update_cols = {
            "price": stmt.inserted.price,
            "rating": stmt.inserted.rating,
            "availability": stmt.inserted.availability,
            "source_url": stmt.inserted.source_url,
        }
        stmt = stmt.on_duplicate_key_update(**update_cols)
        try:
            session.execute(stmt)
            inserted += 1
        except Exception as e:
            logger.warning(f"Book insert failed for '{title}': {e}")
    return inserted

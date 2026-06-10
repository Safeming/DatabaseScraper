"""商品入库:products + brands(维表)+ 触发 price_history。"""
from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from db.models import Product, Brand
from db.value_parsers import parse_price, parse_rating, coerce_str

logger = logging.getLogger(__name__)


def _upsert_brand(session, name: str | None) -> int | None:
    name = coerce_str(name, max_len=100)
    if not name:
        return None
    existing = session.execute(
        select(Brand).where(Brand.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing.id
    brand = Brand(name=name)
    session.add(brand)
    session.flush()
    return brand.id


def store_products(session, job_id: int, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        name = coerce_str(row.get("name") or row.get("title"), max_len=500)
        if not name:
            continue

        brand_id = _upsert_brand(session, row.get("brand"))
        price, currency = parse_price(row.get("price"))
        rating = parse_rating(row.get("rating"))
        sku = coerce_str(row.get("sku"), max_len=100)
        source_url = coerce_str(row.get("url") or row.get("source_url"), max_len=2048)

        stmt = mysql_insert(Product).values(
            job_id=job_id,
            name=name,
            brand_id=brand_id,
            price=price,
            currency=currency or "USD",
            sku=sku,
            rating=rating,
            source_url=source_url,
        )
        stmt = stmt.on_duplicate_key_update(
            price=stmt.inserted.price,
            rating=stmt.inserted.rating,
            sku=stmt.inserted.sku,
            source_url=stmt.inserted.source_url,
        )
        try:
            session.execute(stmt)
            inserted += 1
        except Exception as e:
            logger.warning(f"Product insert failed for '{name}': {e}")
    return inserted

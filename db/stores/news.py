"""新闻入库:news + news_sources(从 URL 推断域名)。"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from db.models import News, NewsSource
from db.value_parsers import parse_date, coerce_str, extract_image_url

logger = logging.getLogger(__name__)


def _upsert_source(session, name: str | None, url: str | None) -> int | None:
    if not name and url:
        try:
            name = urlparse(url).netloc
        except Exception:
            name = None
    name = coerce_str(name, max_len=100)
    if not name:
        return None
    existing = session.execute(
        select(NewsSource).where(NewsSource.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing.id
    src = NewsSource(name=name, url=coerce_str(url, max_len=500))
    session.add(src)
    session.flush()
    return src.id


def store_news(session, job_id: int, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        title = coerce_str(row.get("title"), max_len=500)
        if not title:
            continue

        author = coerce_str(row.get("author"), max_len=200)
        url = coerce_str(row.get("url"), max_len=2048)
        source_name = coerce_str(row.get("source"))
        source_id = _upsert_source(session, source_name, url)
        publish_date = parse_date(row.get("publish_date") or row.get("date"))
        summary = coerce_str(row.get("summary") or row.get("description"))
        cover_image_url = extract_image_url(row)

        stmt = mysql_insert(News).values(
            job_id=job_id,
            title=title,
            author=author,
            source_id=source_id,
            publish_date=publish_date,
            summary=summary,
            url=url,
            cover_image_url=cover_image_url,
        )
        # url_hash 是 generated 列,自动从 url 算 SHA256;这里依赖它做去重
        stmt = stmt.on_duplicate_key_update(
            title=stmt.inserted.title,
            summary=stmt.inserted.summary,
            publish_date=stmt.inserted.publish_date,
            cover_image_url=stmt.inserted.cover_image_url,
        )
        try:
            session.execute(stmt)
            inserted += 1
        except Exception as e:
            logger.warning(f"News insert failed for '{title}': {e}")
    return inserted

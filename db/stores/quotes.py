"""名言入库:quotes + authors + tags(多对多)。"""
from __future__ import annotations

import logging
import re
from sqlalchemy import select

from db.models import Quote, Author, Tag, QuoteTag
from db.value_parsers import coerce_str

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


def _upsert_tag(session, name: str) -> int | None:
    name = coerce_str(name, max_len=50)
    if not name:
        return None
    existing = session.execute(
        select(Tag).where(Tag.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing.id
    tag = Tag(name=name)
    session.add(tag)
    session.flush()
    return tag.id


def _split_tags(raw) -> list[str]:
    """'love, life, inspiration' / ['love','life'] -> ['love', 'life', 'inspiration']"""
    if raw is None:
        return []
    if isinstance(raw, list):
        items = raw
    else:
        items = re.split(r"[,;|]", str(raw))
    return [t.strip() for t in items if t and t.strip()]


def store_quotes(session, job_id: int, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        text = coerce_str(row.get("quote") or row.get("text"))
        if not text:
            continue

        author_id = _upsert_author(session, row.get("author"))
        source_url = coerce_str(row.get("url") or row.get("source_url"), max_len=2048)

        # 名言无天然 unique key,直接插入(避免误合并不同语境的同句)
        quote = Quote(
            job_id=job_id,
            quote=text,
            author_id=author_id,
            source_url=source_url,
        )
        session.add(quote)
        session.flush()

        # 关联标签
        for tname in _split_tags(row.get("tags")):
            tag_id = _upsert_tag(session, tname)
            if tag_id is None:
                continue
            link = QuoteTag(quote_id=quote.id, tag_id=tag_id)
            session.merge(link)

        inserted += 1
    return inserted

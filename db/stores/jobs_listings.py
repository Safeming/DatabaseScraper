"""招聘信息入库:jobs_listings 表。"""
from __future__ import annotations

import logging
from sqlalchemy.dialects.mysql import insert as mysql_insert

from db.models import JobListing
from db.value_parsers import parse_date, coerce_str

logger = logging.getLogger(__name__)


def store_jobs_listings(session, job_id: int, rows: list[dict]) -> int:
    inserted = 0
    for row in rows:
        title = coerce_str(row.get("job_title") or row.get("title"), max_len=300)
        if not title:
            continue

        company = coerce_str(row.get("company"), max_len=200)
        location = coerce_str(row.get("location"), max_len=200)
        salary = coerce_str(row.get("salary"), max_len=100)
        post_date = parse_date(row.get("post_date") or row.get("date"))
        source_url = coerce_str(row.get("url") or row.get("source_url"), max_len=2048)

        stmt = mysql_insert(JobListing).values(
            job_id=job_id,
            job_title=title,
            company=company,
            location=location,
            salary=salary,
            post_date=post_date,
            source_url=source_url,
        )
        stmt = stmt.on_duplicate_key_update(
            salary=stmt.inserted.salary,
            post_date=stmt.inserted.post_date,
            source_url=stmt.inserted.source_url,
        )
        try:
            session.execute(stmt)
            inserted += 1
        except Exception as e:
            logger.warning(f"JobListing insert failed for '{title}': {e}")
    return inserted

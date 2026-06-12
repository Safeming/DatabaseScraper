"""数据访问层。保持与原 database.py 完全相同的函数签名,
内部走 SQLAlchemy + MySQL。所有调用方零改动。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from sqlalchemy import select, text, func, and_
from sqlalchemy.exc import SQLAlchemyError

from .connection import get_engine, get_session
from .models import (
    Job, Result, Category, Book, Author, Quote, QuoteTag, Tag,
    Product, Brand, News, JobListing, GenericItem, PriceHistory
)
from .stores import store_by_category

logger = logging.getLogger(__name__)


# ─── 类别字典 ───

def _resolve_category_id(session, code: str | None) -> int | None:
    if not code:
        return None
    cat = session.execute(
        select(Category).where(Category.code == code)
    ).scalar_one_or_none()
    return cat.id if cat else None


# ─── 初始化 ───

def init_db():
    """检查 MySQL 是否可达;如果未建库会失败,提示用户先跑 schema.sql。"""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1 FROM categories LIMIT 1"))
    except SQLAlchemyError as e:
        logger.error(
            "MySQL not initialized. Please run: "
            "mysql -u root -p --default-character-set=utf8mb4 < db/schema.sql"
        )
        raise RuntimeError(f"DB init check failed: {e}") from e


# ─── Job CRUD ───

def create_job(name, urls, query, method="Crawl4AI", llm_provider="Ollama",
               llm_model=None, follow_pagination=False, max_pages=5,
               schedule_cron=None, pipeline_config=None, category_code=None):
    with get_session() as s:
        category_id = _resolve_category_id(s, category_code)
        job = Job(
            name=name,
            status="pending",
            category_id=category_id,
            method=method,
            llm_provider=llm_provider,
            llm_model=llm_model,
            follow_pagination=1 if follow_pagination else 0,
            max_pages=max_pages,
            schedule_cron=schedule_cron,
            pipeline_config=pipeline_config if isinstance(pipeline_config, (dict, list)) else None,
            urls=urls if isinstance(urls, list) else json.loads(urls or "[]"),
            query=query,
        )
        s.add(job)
        s.flush()
        return job.id


def _job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "status": job.status,
        "category_id": job.category_id,
        "method": job.method,
        "llm_provider": job.llm_provider,
        "llm_model": job.llm_model,
        "follow_pagination": job.follow_pagination,
        "max_pages": job.max_pages,
        "schedule_cron": job.schedule_cron,
        "pipeline_config": json.dumps(job.pipeline_config, ensure_ascii=False) if job.pipeline_config else None,
        "urls": json.dumps(job.urls, ensure_ascii=False) if job.urls else "[]",
        "query": job.query,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error_message": job.error_message,
    }


def get_job(job_id):
    with get_session() as s:
        job = s.get(Job, job_id)
        return _job_to_dict(job) if job else None


def list_jobs(status=None, limit=50):
    with get_session() as s:
        stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(Job.status == status)
        jobs = s.execute(stmt).scalars().all()
        return [_job_to_dict(j) for j in jobs]


def update_job_status(job_id, status, error=None):
    with get_session() as s:
        job = s.get(Job, job_id)
        if not job:
            return
        now = datetime.now()
        job.status = status
        if status == "running":
            job.started_at = now
        elif status in ("completed", "failed"):
            job.completed_at = now
            if error:
                job.error_message = error


def update_job_category(job_id: int, category_code: str):
    """智能模式分类完成后回写到 jobs.category_id(只写一次)。"""
    with get_session() as s:
        job = s.get(Job, job_id)
        if not job or job.category_id:
            return
        cid = _resolve_category_id(s, category_code)
        if cid:
            job.category_id = cid


def delete_job(job_id):
    with get_session() as s:
        job = s.get(Job, job_id)
        if job:
            s.delete(job)  # cascade 自动清理 results


# ─── Results CRUD ───

def add_result(job_id, url, page_number=1):
    with get_session() as s:
        r = Result(job_id=job_id, url=url, page_number=page_number)
        s.add(r)
        s.flush()
        return r.id


def update_result(result_id, **kwargs):
    with get_session() as s:
        r = s.get(Result, result_id)
        if not r:
            return
        for k, v in kwargs.items():
            if hasattr(r, k):
                setattr(r, k, v)


def _result_to_dict(r: Result) -> dict:
    return {
        "id": r.id,
        "job_id": r.job_id,
        "url": r.url,
        "page_number": r.page_number,
        "raw_markdown": r.raw_markdown,
        "extracted_csv": r.extracted_csv,
        "row_count": r.row_count,
        "status": r.status,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def get_results_for_job(job_id):
    with get_session() as s:
        rows = s.execute(
            select(Result).where(Result.job_id == job_id)
            .order_by(Result.url, Result.page_number)
        ).scalars().all()
        return [_result_to_dict(r) for r in rows]


# ─── Extracted Data ───

def store_extracted_rows(job_id, result_id, rows, category=None):
    """根据 category 路由到专属表;result_id 仅用于更新 row_count。"""
    if not rows:
        return 0
    with get_session() as s:
        # 如果未指定 category,从 jobs.category 反查
        if not category:
            job = s.get(Job, job_id)
            if job and job.category_id:
                cat = s.get(Category, job.category_id)
                category = cat.code if cat else None

        n = store_by_category(s, job_id, rows, category)

        # 更新 results.row_count
        r = s.get(Result, result_id) if result_id else None
        if r:
            r.row_count = n
        return n


def _book_to_dict(b: Book) -> dict:
    return {
        "title": b.title,
        "author": b.author.name if b.author else None,
        "price": float(b.price) if b.price else None,
        "currency": b.currency,
        "rating": b.rating,
        "availability": b.availability,
        "url": b.source_url,
        "cover_image_url": b.cover_image_url,
    }


def _quote_to_dict(q: Quote) -> dict:
    return {
        "quote": q.quote,
        "author": q.author.name if q.author else None,
        "url": q.source_url,
    }


def _product_to_dict(p: Product) -> dict:
    return {
        "name": p.name,
        "brand": p.brand.name if p.brand else None,
        "price": float(p.price) if p.price else None,
        "currency": p.currency,
        "sku": p.sku,
        "rating": float(p.rating) if p.rating else None,
        "url": p.source_url,
        "image_url": p.image_url,
    }


def _news_to_dict(n: News) -> dict:
    return {
        "title": n.title,
        "author": n.author,
        "source": n.source.name if n.source else None,
        "publish_date": n.publish_date.isoformat() if n.publish_date else None,
        "summary": n.summary,
        "url": n.url,
        "cover_image_url": n.cover_image_url,
    }


def _job_listing_to_dict(jl: JobListing) -> dict:
    return {
        "job_title": jl.job_title,
        "company": jl.company,
        "location": jl.location,
        "salary": jl.salary,
        "post_date": jl.post_date.isoformat() if jl.post_date else None,
        "url": jl.source_url,
    }


def get_job_data(job_id):
    """从所有可能的业务表 + generic_items 收集该 job 的数据,合并成 list[dict]。
    用于 pipeline 的去重比对 + 历史页 dataframe 展示。"""
    out: list[dict] = []
    with get_session() as s:
        for b in s.execute(select(Book).where(Book.job_id == job_id)).scalars():
            out.append(_book_to_dict(b))
        for q in s.execute(select(Quote).where(Quote.job_id == job_id)).scalars():
            out.append(_quote_to_dict(q))
        for p in s.execute(select(Product).where(Product.job_id == job_id)).scalars():
            out.append(_product_to_dict(p))
        for n in s.execute(select(News).where(News.job_id == job_id)).scalars():
            out.append(_news_to_dict(n))
        for jl in s.execute(select(JobListing).where(JobListing.job_id == job_id)).scalars():
            out.append(_job_listing_to_dict(jl))
        for g in s.execute(select(GenericItem).where(GenericItem.job_id == job_id)).scalars():
            out.append(g.data_json if isinstance(g.data_json, dict) else json.loads(g.data_json))
    return out


def get_job_dataframe(job_id):
    data = get_job_data(job_id)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def export_to_excel(job_id, filepath):
    df = get_job_dataframe(job_id)
    if df.empty:
        return False
    df.to_excel(filepath, index=False, engine="openpyxl")
    return True


# ─── Scheduling helpers ───

def get_pending_jobs():
    return list_jobs(status="pending")


def get_scheduled_jobs():
    with get_session() as s:
        rows = s.execute(
            select(Job).where(
                and_(Job.schedule_cron.isnot(None), Job.status != "running")
            )
        ).scalars().all()
        return [_job_to_dict(j) for j in rows]

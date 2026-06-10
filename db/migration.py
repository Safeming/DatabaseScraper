"""老 SQLite 数据 → MySQL 迁移脚本。

用法:
    python -m db.migration               # 默认从 ./rpa_data.db 迁出
    python -m db.migration --db <path>   # 指定 SQLite 文件
    python -m db.migration --dry-run     # 只预览不写

策略:
- jobs / results 1:1 复制 (保留 id 以维持外键关联)
- extracted_data 的 data_json:按 jobs.query 推断 category 后路由到专属表

类别推断启发式:
- 如果 jobs.query 命中类别字段子集 → 用对应类别
- 否则 → 'general'
"""
from __future__ import annotations

import json
import logging
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

from sqlalchemy import text

from .connection import get_engine, get_session
from .models import Job, Result
from .stores import store_by_category

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


# 类别推断规则:query 中包含的字段 → category
# 顺序很重要:更专业的字段(quote/sku/abstract...)放前面优先匹配
CATEGORY_HINTS = [
    ("quotes",   {"quote", "tags"}),
    ("products", {"sku", "brand"}),
    ("papers",   {"abstract", "venue", "doi"}),
    ("movies",   {"director", "genre"}),
    ("jobs",     {"job_title", "company", "salary"}),
    ("news",     {"summary", "publish_date", "publish"}),
    ("books",    {"isbn", "availability"}),
    # 通用关键词放最后(title/author 多类共享,信号弱)
    ("books",    {"title", "author", "price", "rating"}),
]


def infer_category(query: str | None) -> str:
    if not query:
        return "general"
    q_fields = {f.strip().lower() for f in query.split(",") if f.strip()}
    best, score = "general", 0
    for cat, fields in CATEGORY_HINTS:
        s = len(q_fields & fields)
        if s > score:
            best, score = cat, s
    return best


def _resolve_category_id(s, code: str) -> int | None:
    row = s.execute(text("SELECT id FROM categories WHERE code=:c"), {"c": code}).first()
    return row[0] if row else None


def _safe_dt(value) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def migrate(sqlite_path: Path, dry_run: bool = False) -> dict:
    """主流程。返回 {'jobs': N, 'results': M, 'rows': K, 'failed': F}."""
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")

    src = sqlite3.connect(str(sqlite_path))
    src.row_factory = sqlite3.Row

    stats = {"jobs": 0, "results": 0, "rows": 0, "failed": 0}
    failed_rows: list[dict] = []

    with get_session() as s:
        # ---- 迁移 jobs ----
        jobs = src.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        logger.info(f"Found {len(jobs)} jobs in SQLite")
        for j in jobs:
            cat_code = infer_category(j["query"])
            cat_id = _resolve_category_id(s, cat_code)

            try:
                urls = json.loads(j["urls"]) if j["urls"] else []
            except Exception:
                urls = [j["urls"]] if j["urls"] else []

            try:
                pcfg = json.loads(j["pipeline_config"]) if j["pipeline_config"] else None
            except Exception:
                pcfg = None

            # MySQL 插入(用 ON DUPLICATE KEY UPDATE 防重复迁移)
            if not dry_run:
                s.execute(text("""
                    INSERT INTO jobs (id, name, status, category_id, method, llm_provider, llm_model,
                                      follow_pagination, max_pages, schedule_cron, pipeline_config, urls,
                                      `query`, created_at, started_at, completed_at, error_message)
                    VALUES (:id, :name, :status, :category_id, :method, :llm_provider, :llm_model,
                            :follow_pagination, :max_pages, :schedule_cron, :pipeline_config, :urls,
                            :query, :created_at, :started_at, :completed_at, :error_message)
                    ON DUPLICATE KEY UPDATE
                        status = VALUES(status),
                        category_id = VALUES(category_id),
                        completed_at = VALUES(completed_at)
                """), {
                    "id": j["id"],
                    "name": j["name"],
                    "status": j["status"] or "completed",
                    "category_id": cat_id,
                    "method": j["method"],
                    "llm_provider": j["llm_provider"],
                    "llm_model": j["llm_model"],
                    "follow_pagination": j["follow_pagination"] or 0,
                    "max_pages": j["max_pages"] or 5,
                    "schedule_cron": j["schedule_cron"],
                    "pipeline_config": json.dumps(pcfg, ensure_ascii=False) if pcfg else None,
                    "urls": json.dumps(urls, ensure_ascii=False),
                    "query": j["query"],
                    "created_at": _safe_dt(j["created_at"]),
                    "started_at": _safe_dt(j["started_at"]),
                    "completed_at": _safe_dt(j["completed_at"]),
                    "error_message": j["error_message"],
                })
            stats["jobs"] += 1

        # ---- 迁移 results ----
        results = src.execute("SELECT * FROM results ORDER BY id").fetchall()
        logger.info(f"Found {len(results)} results in SQLite")
        for r in results:
            if not dry_run:
                s.execute(text("""
                    INSERT INTO results (id, job_id, url, page_number, raw_markdown, extracted_csv,
                                         row_count, status, error_message, created_at)
                    VALUES (:id, :job_id, :url, :page_number, :raw_markdown, :extracted_csv,
                            :row_count, :status, :error_message, :created_at)
                    ON DUPLICATE KEY UPDATE row_count = VALUES(row_count), status = VALUES(status)
                """), {
                    "id": r["id"],
                    "job_id": r["job_id"],
                    "url": r["url"],
                    "page_number": r["page_number"] or 1,
                    "raw_markdown": r["raw_markdown"],
                    "extracted_csv": r["extracted_csv"],
                    "row_count": r["row_count"] or 0,
                    "status": r["status"] or "stored",
                    "error_message": r["error_message"],
                    "created_at": _safe_dt(r["created_at"]),
                })
            stats["results"] += 1

        # ---- 迁移 extracted_data → 类别专属表 ----
        # 按 job_id 分组,一次取一个 job 的所有 row 走 store_by_category
        rows_by_job: dict[int, list[dict]] = {}
        ed_query = "SELECT job_id, data_json FROM extracted_data ORDER BY job_id, id"
        for ed in src.execute(ed_query).fetchall():
            try:
                row = json.loads(ed["data_json"])
            except Exception as e:
                stats["failed"] += 1
                failed_rows.append({"reason": f"json parse: {e}", "raw": ed["data_json"]})
                continue
            rows_by_job.setdefault(ed["job_id"], []).append(row)

        # 重新查 jobs 拿到每个 job 的 query → 推断 category
        job_categories = {
            j["id"]: infer_category(j["query"])
            for j in jobs
        }

        for job_id, rows in rows_by_job.items():
            cat = job_categories.get(job_id, "general")
            logger.info(f"Migrating job {job_id}: {len(rows)} rows -> category '{cat}'")
            if not dry_run:
                try:
                    n = store_by_category(s, job_id, rows, cat)
                    stats["rows"] += n
                except Exception as e:
                    logger.error(f"Job {job_id} failed: {e}")
                    stats["failed"] += len(rows)
                    failed_rows.extend([{"reason": str(e), "job_id": job_id, "row": r} for r in rows])
            else:
                stats["rows"] += len(rows)

    src.close()

    if failed_rows and not dry_run:
        out = Path("migration_failed.json")
        out.write_text(json.dumps(failed_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.warning(f"{len(failed_rows)} rows failed; saved to {out}")

    return stats


def main():
    ap = argparse.ArgumentParser(description="Migrate legacy SQLite data to MySQL.")
    ap.add_argument("--db", type=Path, default=Path("rpa_data.db"),
                    help="Path to legacy SQLite file (default: rpa_data.db)")
    ap.add_argument("--dry-run", action="store_true", help="Preview only, don't write")
    args = ap.parse_args()

    print(f"Source: {args.db.absolute()}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 50)

    stats = migrate(args.db, dry_run=args.dry_run)

    print("-" * 50)
    print(f"Migrated jobs:    {stats['jobs']}")
    print(f"Migrated results: {stats['results']}")
    print(f"Migrated rows:    {stats['rows']}")
    print(f"Failed rows:      {stats['failed']}")


if __name__ == "__main__":
    main()

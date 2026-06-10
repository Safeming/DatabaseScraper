import os
import json
import sqlite3
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rpa_data.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            urls TEXT NOT NULL,
            query TEXT NOT NULL,
            method TEXT DEFAULT 'Crawl4AI',
            llm_provider TEXT DEFAULT 'Ollama',
            llm_model TEXT,
            follow_pagination INTEGER DEFAULT 0,
            max_pages INTEGER DEFAULT 5,
            schedule_cron TEXT,
            pipeline_config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            page_number INTEGER DEFAULT 1,
            raw_markdown TEXT,
            extracted_csv TEXT,
            row_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS extracted_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            result_id INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (job_id) REFERENCES jobs(id),
            FOREIGN KEY (result_id) REFERENCES results(id)
        );
    """)
    conn.commit()
    conn.close()


# ─── Job CRUD ───

def create_job(name, urls, query, method="Crawl4AI", llm_provider="Ollama",
               llm_model=None, follow_pagination=False, max_pages=5,
               schedule_cron=None, pipeline_config=None):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO jobs (name, urls, query, method, llm_provider, llm_model,
                          follow_pagination, max_pages, schedule_cron, pipeline_config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        json.dumps(urls) if isinstance(urls, list) else urls,
        query, method, llm_provider, llm_model,
        1 if follow_pagination else 0,
        max_pages, schedule_cron,
        json.dumps(pipeline_config) if pipeline_config else None
    ))
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    return job_id


def get_job(job_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_jobs(status=None, limit=50):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_job_status(job_id, status, error=None):
    conn = get_connection()
    now = datetime.now().isoformat()
    if status == "running":
        conn.execute("UPDATE jobs SET status=?, started_at=? WHERE id=?",
                     (status, now, job_id))
    elif status in ("completed", "failed"):
        conn.execute("UPDATE jobs SET status=?, completed_at=?, error_message=? WHERE id=?",
                     (status, now, error, job_id))
    else:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))
    conn.commit()
    conn.close()


def delete_job(job_id):
    conn = get_connection()
    conn.execute("DELETE FROM extracted_data WHERE job_id=?", (job_id,))
    conn.execute("DELETE FROM results WHERE job_id=?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()


# ─── Results CRUD ───

def add_result(job_id, url, page_number=1):
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO results (job_id, url, page_number) VALUES (?, ?, ?)",
        (job_id, url, page_number)
    )
    conn.commit()
    result_id = cur.lastrowid
    conn.close()
    return result_id


def update_result(result_id, **kwargs):
    conn = get_connection()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [result_id]
    conn.execute(f"UPDATE results SET {sets} WHERE id=?", values)
    conn.commit()
    conn.close()


def get_results_for_job(job_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM results WHERE job_id=? ORDER BY url, page_number", (job_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Extracted Data ───

def store_extracted_rows(job_id, result_id, rows):
    conn = get_connection()
    for row in rows:
        conn.execute(
            "INSERT INTO extracted_data (job_id, result_id, data_json) VALUES (?, ?, ?)",
            (job_id, result_id, json.dumps(row, ensure_ascii=False))
        )
    conn.execute("UPDATE results SET row_count=? WHERE id=?", (len(rows), result_id))
    conn.commit()
    conn.close()


def get_job_data(job_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT data_json FROM extracted_data WHERE job_id=? ORDER BY id", (job_id,)
    ).fetchall()
    conn.close()
    return [json.loads(r["data_json"]) for r in rows]


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
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE schedule_cron IS NOT NULL AND status != 'running'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

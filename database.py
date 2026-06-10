"""向后兼容 shim。所有原有调用方(app.py / pipeline.py / pages/* / scheduler.py)
通过 `from database import xxx` 导入的函数,现在全部转发到 db.repository。

旧 SQLite 实现已备份到 db/_legacy_sqlite.py,迁移脚本会读取它来导入历史数据。
"""
from db.repository import (
    init_db,
    create_job,
    get_job,
    list_jobs,
    update_job_status,
    update_job_category,
    delete_job,
    add_result,
    update_result,
    get_results_for_job,
    store_extracted_rows,
    get_job_data,
    get_job_dataframe,
    export_to_excel,
    get_pending_jobs,
    get_scheduled_jobs,
)

__all__ = [
    "init_db",
    "create_job",
    "get_job",
    "list_jobs",
    "update_job_status",
    "update_job_category",
    "delete_job",
    "add_result",
    "update_result",
    "get_results_for_job",
    "store_extracted_rows",
    "get_job_data",
    "get_job_dataframe",
    "export_to_excel",
    "get_pending_jobs",
    "get_scheduled_jobs",
]

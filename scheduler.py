import time
import logging
import schedule
from datetime import datetime
from croniter import croniter

from database import init_db, get_pending_jobs, get_scheduled_jobs, update_job_status
from pipeline import execute_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def run_pending_jobs():
    jobs = get_pending_jobs()
    for job in jobs:
        if job.get("schedule_cron"):
            continue
        logger.info(f"Executing job #{job['id']}: {job['name']}")
        execute_pipeline(job)


def run_scheduled_jobs():
    jobs = get_scheduled_jobs()
    now = datetime.now()

    for job in jobs:
        cron_expr = job.get("schedule_cron")
        if not cron_expr:
            continue

        last_run = job.get("completed_at") or job.get("created_at")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
            except (ValueError, TypeError):
                last_dt = datetime(2000, 1, 1)
        else:
            last_dt = datetime(2000, 1, 1)

        try:
            cron = croniter(cron_expr, last_dt)
            next_run = cron.get_next(datetime)
            if next_run <= now and job["status"] != "running":
                logger.info(f"Scheduled job #{job['id']} triggered: {job['name']}")
                update_job_status(job["id"], "pending")
                execute_pipeline(job)
        except Exception as e:
            logger.error(f"Error checking schedule for job #{job['id']}: {e}")


def main():
    init_db()
    logger.info("=" * 50)
    logger.info("RPA Scheduler started. Watching for jobs...")
    logger.info("=" * 50)

    schedule.every(10).seconds.do(run_pending_jobs)
    schedule.every(1).minutes.do(run_scheduled_jobs)

    while True:
        schedule.run_pending()
        time.sleep(5)


if __name__ == "__main__":
    main()

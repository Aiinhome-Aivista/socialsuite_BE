"""
Scheduler for future-dated posts. Uses APScheduler with a MySQL jobstore so
jobs survive restarts — no Docker / no Redis needed for the starter setup.

For high volume / guaranteed retries later, swap to Celery + a natively
installed Redis. The publish function stays the same.

Run as its own systemd service (see deploy/) so the web workers stay light:
    python -m app.worker
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from app.config import settings
from app.services.publisher import publish_post

jobstores = {"default": SQLAlchemyJobStore(url=settings.database_url)}
scheduler = BackgroundScheduler(jobstores=jobstores, timezone="UTC")


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()


def schedule_post(post_id: int, run_at) -> str:
    """Schedule (or reschedule) a post. Returns the APScheduler job id."""
    job_id = f"post:{post_id}"
    scheduler.add_job(
        publish_post,
        trigger="date",
        run_date=run_at,
        args=[post_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return job_id


def cancel_scheduled_post(post_id: int) -> None:
    try:
        scheduler.remove_job(f"post:{post_id}")
    except Exception:
        pass

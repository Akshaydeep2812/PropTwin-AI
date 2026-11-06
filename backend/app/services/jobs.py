"""A small database-backed job queue with retries and backoff."""

import uuid
from collections.abc import Callable
from datetime import timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BackgroundJob
from app.models.types import utcnow

log = structlog.get_logger("proptwin.jobs")
BASE_BACKOFF_SECONDS = 15


def enqueue(db: Session, kind: str, payload: dict) -> BackgroundJob:
    job = BackgroundJob(kind=kind, payload=payload, run_after=utcnow())
    db.add(job)
    return job


def claim_next(db: Session) -> BackgroundJob | None:
    """SKIP LOCKED lets several workers share the queue without taking the same job."""
    job = db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.status == "queued", BackgroundJob.run_after <= utcnow())
        .order_by(BackgroundJob.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.attempts += 1
    db.commit()
    return job


def run_one(db: Session, handlers: dict[str, Callable[[Session, dict], None]]) -> bool:
    """Runs one due job, returning False when none is due. A failure rolls back all of the job's own work."""
    job = claim_next(db)
    if job is None:
        return False
    job_id: uuid.UUID = job.id
    try:
        handler = handlers.get(job.kind)
        if handler is None:
            raise ValueError(f"No handler for job kind {job.kind}")
        handler(db, job.payload)
        job = db.get(BackgroundJob, job_id)
        job.status = "succeeded"
        job.last_error = None
        db.commit()
    except Exception as exc:  # A bad job must never stop the worker loop.
        db.rollback()
        job = db.get(BackgroundJob, job_id)
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        if job.attempts >= get_settings().job_max_attempts:
            job.status = "dead"
        else:
            job.status = "queued"
            job.run_after = utcnow() + timedelta(seconds=BASE_BACKOFF_SECONDS * 2 ** (job.attempts - 1))
        db.commit()
        log.warning("job_failed", job_id=str(job_id), kind=job.kind, attempts=job.attempts, status=job.status)
    return True

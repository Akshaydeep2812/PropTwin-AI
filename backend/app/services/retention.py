"""Deletes data past its retention period. Valuations, snapshots, simulations and chain records are never purged here."""

from datetime import timedelta

import structlog
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AccountToken, AuditLog, BackgroundJob, Notification, RefreshToken
from app.models.types import utcnow

log = structlog.get_logger("proptwin.retention")
EXPIRED_TOKEN_GRACE = timedelta(days=30)
READ_NOTIFICATION_AGE = timedelta(days=365)
FINISHED_JOB_AGE = timedelta(days=30)
RUN_INTERVAL = timedelta(days=1)

_last_run = None


def purge(db: Session) -> dict[str, int]:
    now = utcnow()
    statements = {
        "audit_logs": delete(AuditLog).where(AuditLog.created_at < now - timedelta(days=get_settings().audit_retention_days)),
        "refresh_tokens": delete(RefreshToken).where(RefreshToken.expires_at < now - EXPIRED_TOKEN_GRACE),
        "account_tokens": delete(AccountToken).where(AccountToken.expires_at < now - EXPIRED_TOKEN_GRACE),
        "notifications": delete(Notification).where(Notification.read_at.is_not(None), Notification.read_at < now - READ_NOTIFICATION_AGE),
        # Dead jobs are kept: they are failures an operator still needs to see.
        "background_jobs": delete(BackgroundJob).where(BackgroundJob.status == "succeeded", BackgroundJob.updated_at < now - FINISHED_JOB_AGE),
    }
    counts = {name: db.execute(statement).rowcount for name, statement in statements.items()}
    db.commit()
    log.info("retention_purge", **counts)
    return counts


def purge_if_due(db: Session) -> None:
    global _last_run
    now = utcnow()
    if _last_run is None or now - _last_run >= RUN_INTERVAL:
        purge(db)
        _last_run = now

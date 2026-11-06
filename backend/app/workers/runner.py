"""Background loop started with the API. Each pass handles due jobs, then reconciles open chain transactions."""

import threading
import uuid
from collections.abc import Callable

import structlog
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.types import utcnow
from app.services import blockchain_service, jobs, retention, twin_service

log = structlog.get_logger("proptwin.worker")
MAX_JOBS_PER_PASS = 50


def _revalue(db: Session, payload: dict) -> None:
    twin_service.revalue(db, uuid.UUID(payload["property_id"]))
    db.commit()


HANDLERS: dict[str, Callable[[Session, dict], None]] = {"twin_revalue": _revalue}
PERIODIC: list[Callable[[Session], None]] = [blockchain_service.reconcile_open_transactions, retention.purge_if_due]


def run_pass(db: Session) -> int:
    processed = 0
    while processed < MAX_JOBS_PER_PASS and jobs.run_one(db, HANDLERS):
        processed += 1
    for task in PERIODIC:
        try:
            task(db)
        except Exception as exc:
            db.rollback()
            log.warning("periodic_task_failed", task=task.__name__, error=str(exc))
    return processed


class Worker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="proptwin-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)

    def _loop(self) -> None:
        interval = get_settings().worker_poll_seconds
        while not self._stop.wait(interval):
            try:
                with SessionLocal() as db:
                    run_pass(db)
            except Exception as exc:
                log.warning("worker_pass_failed", error=str(exc), at=utcnow().isoformat())

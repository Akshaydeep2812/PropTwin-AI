import uuid
from typing import Any

import structlog
from sqlalchemy.orm import Session

from app.models import AuditLog


def record(db: Session, action: str, entity_type: str, entity_id: Any = None, actor_id: uuid.UUID | None = None, **details: Any) -> None:
    """Adds an audit row to the caller's transaction. Never pass secrets or document contents as details."""
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            details=details,
            request_id=request_id,
        )
    )

from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DatabaseSession, Paging
from app.core.errors import not_found
from app.models import Notification
from app.models.types import utcnow
from app.schemas.admin import NotificationRead
from app.schemas.common import Page

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=Page[NotificationRead])
def list_notifications(user: CurrentUser, db: DatabaseSession, paging: Paging, unread_only: bool = False) -> dict:
    conditions = [Notification.user_id == user.id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    total = db.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    items = db.scalars(
        select(Notification).where(*conditions).order_by(Notification.created_at.desc()).offset((paging.page - 1) * paging.page_size).limit(paging.page_size)
    ).all()
    return {"items": list(items), "page": paging.page, "page_size": paging.page_size, "total": total}


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: UUID, user: CurrentUser, db: DatabaseSession) -> Notification:
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise not_found("Notification")
    notification.read_at = notification.read_at or utcnow()
    db.commit()
    db.refresh(notification)
    return notification

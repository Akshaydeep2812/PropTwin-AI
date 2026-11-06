from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.dependencies import DatabaseSession, Paging, ReviewerUser
from app.models import Property, PropertyVerificationRequest
from app.schemas.common import Page
from app.schemas.property import VerificationDecision, VerificationRead
from app.services import property_service

router = APIRouter(prefix="/verification", tags=["verification"])


@router.get("/queue", response_model=Page[VerificationRead])
def verification_queue(user: ReviewerUser, db: DatabaseSession, paging: Paging, status: str = "pending") -> dict:
    conditions = [PropertyVerificationRequest.status == status]
    total = db.scalar(select(func.count()).select_from(PropertyVerificationRequest).where(*conditions)) or 0
    items = db.scalars(
        select(PropertyVerificationRequest)
        .where(*conditions)
        .order_by(PropertyVerificationRequest.created_at)
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
    ).all()
    ids = [item.property_id for item in items]
    titles = {row.id: row.title for row in db.execute(select(Property.id, Property.title).where(Property.id.in_(ids)))} if ids else {}
    rows = [VerificationRead.model_validate(item).model_copy(update={"property_title": titles.get(item.property_id)}) for item in items]
    return {"items": rows, "page": paging.page, "page_size": paging.page_size, "total": total}


@router.post("/{request_id}/decision", response_model=VerificationRead)
def decide(request_id: UUID, payload: VerificationDecision, user: ReviewerUser, db: DatabaseSession):
    return property_service.decide_verification(db, request_id, user, payload.decision, payload.notes)

from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession, OptionalUser, OwnerUser, Paging
from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import Property, PropertyDocument, PropertyImage, PropertyVerificationRequest, SavedProperty
from app.schemas.common import Page
from app.schemas.insights import PortfolioRead, PropertyInsights
from app.schemas.property import (
    DocumentRead,
    ImageRead,
    PropertyCreate,
    PropertyPublicRead,
    PropertyRead,
    PropertyUpdate,
    RenovationCreate,
    RenovationRead,
    ReportCreate,
    ReportRead,
    VerificationCreate,
    VerificationRead,
)
from app.services import access, audit, insight_service, property_service
from app.services.storage import get_storage

router = APIRouter(prefix="/properties", tags=["properties"])
favorites_router = APIRouter(prefix="/saved-properties", tags=["favorites"])


async def _read_upload(upload: UploadFile) -> bytes:
    # Read one byte past the limit so an oversized file is rejected without loading all of it.
    return await upload.read(get_settings().max_upload_bytes + 1)


@router.get("", response_model=Page[PropertyPublicRead])
def search_properties(
    db: DatabaseSession,
    paging: Paging,
    q: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    property_type: str | None = Query(default=None, max_length=40),
    min_price: Decimal | None = Query(default=None, ge=0),
    max_price: Decimal | None = Query(default=None, ge=0),
    min_area: Decimal | None = Query(default=None, ge=0),
    max_area: Decimal | None = Query(default=None, ge=0),
    min_bedrooms: int | None = Query(default=None, ge=0),
    verified_only: bool = False,
    sort: Literal["newest", "price_asc", "price_desc", "area_asc", "area_desc"] = "newest",
) -> dict:
    items, total = property_service.search_public(
        db,
        query=q,
        city=city,
        property_type=property_type,
        min_price=min_price,
        max_price=max_price,
        min_area=min_area,
        max_area=max_area,
        min_bedrooms=min_bedrooms,
        verified_only=verified_only,
        sort=sort,
        page=paging.page,
        page_size=paging.page_size,
    )
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}


@router.get("/mine", response_model=Page[PropertyRead])
def my_properties(user: CurrentUser, db: DatabaseSession, paging: Paging, include_archived: bool = False) -> dict:
    items, total = property_service.list_owned(db, user, paging.page, paging.page_size, include_archived)
    return {"items": items, "page": paging.page, "page_size": paging.page_size, "total": total}


@router.get("/mine/portfolio", response_model=PortfolioRead)
def my_portfolio(user: CurrentUser, db: DatabaseSession) -> dict:
    return insight_service.portfolio(db, user)


@router.get("/compare", response_model=list[PropertyPublicRead])
def compare_properties(db: DatabaseSession, user: OptionalUser, ids: list[UUID] = Query(min_length=2, max_length=4)) -> list[Property]:
    return [access.get_visible(db, property_id, user) for property_id in ids]


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
def create_property(payload: PropertyCreate, user: OwnerUser, db: DatabaseSession) -> Property:
    return property_service.create_property(db, user, payload.model_dump())


@router.get("/{property_id}", response_model=PropertyRead | PropertyPublicRead)
def get_property(property_id: UUID, db: DatabaseSession, user: OptionalUser):
    prop = access.get_visible(db, property_id, user)
    if access.can_view_full(db, user, prop):
        return PropertyRead.model_validate(prop)
    return PropertyPublicRead.model_validate(prop)


@router.get("/{property_id}/insights", response_model=PropertyInsights)
def property_insights(property_id: UUID, db: DatabaseSession, user: OptionalUser) -> dict:
    return insight_service.build(db, access.get_visible(db, property_id, user), user)


@router.patch("/{property_id}", response_model=PropertyRead)
def update_property(property_id: UUID, payload: PropertyUpdate, user: CurrentUser, db: DatabaseSession) -> Property:
    prop = access.get_managed(db, property_id, user)
    return property_service.update_property(db, prop, user, payload.model_dump(exclude_unset=True))


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_property(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> Response:
    property_service.archive_property(db, access.get_managed(db, property_id, user), user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{property_id}/images", response_model=ImageRead, status_code=status.HTTP_201_CREATED)
async def upload_image(property_id: UUID, user: CurrentUser, db: DatabaseSession, file: UploadFile = File()) -> PropertyImage:
    prop = access.get_managed(db, property_id, user)
    return property_service.add_image(db, prop, user, await _read_upload(file))


@router.get("/{property_id}/images/{image_id}")
def get_image(property_id: UUID, image_id: UUID, db: DatabaseSession, user: OptionalUser) -> Response:
    access.get_visible(db, property_id, user)
    image = db.get(PropertyImage, image_id)
    if image is None or image.property_id != property_id:
        raise not_found("Image")
    return Response(get_storage().read(image.storage_key), media_type=image.content_type)


@router.post("/{property_id}/documents", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    property_id: UUID,
    user: CurrentUser,
    db: DatabaseSession,
    file: UploadFile = File(),
    document_type: str = Form(min_length=2, max_length=50, pattern=r"^[a-z_]+$"),
) -> PropertyDocument:
    prop = access.get_managed(db, property_id, user)
    return property_service.add_document(db, prop, user, await _read_upload(file), file.filename or "document", document_type)


@router.get("/{property_id}/documents", response_model=list[DocumentRead])
def list_documents(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> list[PropertyDocument]:
    prop = access.get_for_review(db, property_id, user)
    return list(db.scalars(select(PropertyDocument).where(PropertyDocument.property_id == prop.id).order_by(PropertyDocument.created_at.desc())))


@router.get("/{property_id}/documents/{document_id}")
def download_document(property_id: UUID, document_id: UUID, user: CurrentUser, db: DatabaseSession) -> Response:
    prop = access.get_for_review(db, property_id, user)
    document = db.get(PropertyDocument, document_id)
    if document is None or document.property_id != prop.id:
        raise not_found("Document")
    audit.record(db, "property.document_viewed", "property", prop.id, actor_id=user.id, document_id=str(document.id))
    db.commit()
    return Response(
        get_storage().read(document.storage_key),
        media_type=document.content_type,
        headers={"Content-Disposition": 'attachment; filename="document"', "Cache-Control": "private, no-store"},
    )


@router.post("/{property_id}/renovations", response_model=RenovationRead, status_code=status.HTTP_201_CREATED)
def add_renovation(property_id: UUID, payload: RenovationCreate, user: CurrentUser, db: DatabaseSession):
    return property_service.add_renovation(db, access.get_managed(db, property_id, user), user, payload.model_dump())


@router.post("/{property_id}/report", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def report_property(property_id: UUID, payload: ReportCreate, user: CurrentUser, db: DatabaseSession):
    prop = access.get_visible(db, property_id, user)
    if prop.owner_id == user.id:
        raise AppError(422, "cannot_report_own", "You cannot report your own listing.")
    return property_service.report_property(db, prop, user, payload.reason)


@router.post("/{property_id}/verification-requests", response_model=VerificationRead, status_code=status.HTTP_201_CREATED)
def submit_verification(property_id: UUID, payload: VerificationCreate, user: CurrentUser, db: DatabaseSession):
    return property_service.submit_verification(db, access.get_managed(db, property_id, user), user, payload.notes)


@router.get("/{property_id}/verification-requests", response_model=list[VerificationRead])
def verification_history(property_id: UUID, user: CurrentUser, db: DatabaseSession):
    prop = access.get_for_review(db, property_id, user)
    return list(
        db.scalars(
            select(PropertyVerificationRequest)
            .where(PropertyVerificationRequest.property_id == prop.id)
            .order_by(PropertyVerificationRequest.created_at.desc())
        )
    )


@favorites_router.get("", response_model=list[PropertyPublicRead])
def list_favorites(user: CurrentUser, db: DatabaseSession) -> list[Property]:
    # A saved listing that was later withdrawn disappears here instead of leaking its private state.
    return list(
        db.scalars(
            select(Property)
            .join(SavedProperty, SavedProperty.property_id == Property.id)
            .where(SavedProperty.user_id == user.id, Property.listing_status.in_(access.PUBLIC_STATUSES))
            .order_by(SavedProperty.created_at.desc())
        )
    )


@favorites_router.put("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def save_favorite(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> Response:
    property_service.save_favorite(db, user, access.get_visible(db, property_id, user))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@favorites_router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(property_id: UUID, user: CurrentUser, db: DatabaseSession) -> Response:
    property_service.remove_favorite(db, user, property_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

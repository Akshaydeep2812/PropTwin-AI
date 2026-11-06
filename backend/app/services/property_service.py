import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, conflict, not_found
from app.models import (
    Property,
    PropertyDocument,
    PropertyImage,
    PropertyOwnershipHistory,
    PropertyRenovation,
    PropertyReport,
    PropertyVerificationRequest,
    SavedProperty,
    User,
)
from app.models.types import utcnow
from app.services import access, audit, twin_service
from app.services.notifications import notify
from app.services.storage import get_storage

SORTS = {
    "newest": Property.created_at.desc(),
    "price_asc": Property.asking_price.asc(),
    "price_desc": Property.asking_price.desc(),
    "area_asc": Property.built_up_area_sqft.asc(),
    "area_desc": Property.built_up_area_sqft.desc(),
}
# Changing any of these invalidates a prior human verification decision.
VERIFIED_FIELDS = {"address_line1", "locality", "city", "state", "postal_code", "property_type", "built_up_area_sqft", "land_area_sqft", "construction_year"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
DOCUMENT_TYPES = IMAGE_TYPES | {"application/pdf"}
MAX_IMAGES_PER_PROPERTY = 20


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_public(
    db: Session,
    *,
    query: str | None,
    city: str | None,
    property_type: str | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_area: Decimal | None,
    max_area: Decimal | None,
    min_bedrooms: int | None,
    verified_only: bool,
    sort: str,
    page: int,
    page_size: int,
) -> tuple[list[Property], int]:
    conditions = [Property.listing_status.in_(access.PUBLIC_STATUSES)]
    if query:
        pattern = f"%{escape_like(query)}%"
        conditions.append(
            Property.title.ilike(pattern, escape="\\")
            | Property.locality.ilike(pattern, escape="\\")
            | Property.city.ilike(pattern, escape="\\")
        )
    if city:
        conditions.append(Property.city == city)
    if property_type:
        conditions.append(Property.property_type == property_type)
    if min_price is not None:
        conditions.append(Property.asking_price >= min_price)
    if max_price is not None:
        conditions.append(Property.asking_price <= max_price)
    if min_area is not None:
        conditions.append(Property.built_up_area_sqft >= min_area)
    if max_area is not None:
        conditions.append(Property.built_up_area_sqft <= max_area)
    if min_bedrooms is not None:
        conditions.append(Property.bedrooms >= min_bedrooms)
    if verified_only:
        conditions.append(Property.verification_status == "verified")
    total = db.scalar(select(func.count()).select_from(Property).where(*conditions)) or 0
    items = db.scalars(
        select(Property).where(*conditions).order_by(SORTS[sort], Property.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def list_owned(db: Session, user: User, page: int, page_size: int, include_archived: bool = False) -> tuple[list[Property], int]:
    conditions = [Property.owner_id == user.id]
    if not include_archived:
        conditions.append(Property.listing_status != "archived")
    total = db.scalar(select(func.count()).select_from(Property).where(*conditions)) or 0
    items = db.scalars(
        select(Property).where(*conditions).order_by(Property.created_at.desc(), Property.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return list(items), total


def create_property(db: Session, user: User, data: dict) -> Property:
    prop = Property(owner_id=user.id, **data)
    db.add(prop)
    db.flush()
    db.add(PropertyOwnershipHistory(property_id=prop.id, owner_id=user.id, source="registration", effective_from=utcnow()))
    audit.record(db, "property.created", "property", prop.id, actor_id=user.id)
    db.commit()
    db.refresh(prop)
    return prop


def update_property(db: Session, prop: Property, user: User, changes: dict) -> Property:
    changed = sorted(field for field, value in changes.items() if getattr(prop, field) != value)
    for field in changed:
        setattr(prop, field, changes[field])
    if changed and prop.verification_status == "verified" and VERIFIED_FIELDS.intersection(changed):
        prop.verification_status = "unverified"
        audit.record(db, "property.verification_reset", "property", prop.id, actor_id=user.id, fields=sorted(VERIFIED_FIELDS.intersection(changed)))
    if changed:
        audit.record(db, "property.updated", "property", prop.id, actor_id=user.id, fields=changed)
        db.flush()
        twin_service.sync_from_property(db, prop, user.id, changed)
    db.commit()
    db.refresh(prop)
    return prop


def archive_property(db: Session, prop: Property, user: User) -> None:
    prop.listing_status = "archived"
    audit.record(db, "property.archived", "property", prop.id, actor_id=user.id)
    db.flush()
    twin_service.sync_from_property(db, prop, user.id, ["listing_status"])
    db.commit()


def add_image(db: Session, prop: Property, user: User, data: bytes) -> PropertyImage:
    count = db.scalar(select(func.count()).select_from(PropertyImage).where(PropertyImage.property_id == prop.id)) or 0
    if count >= MAX_IMAGES_PER_PROPERTY:
        raise conflict("too_many_images", f"A property may have at most {MAX_IMAGES_PER_PROPERTY} images.")
    stored = get_storage().save(data, IMAGE_TYPES, f"images/{prop.id}")
    image = PropertyImage(property_id=prop.id, storage_key=stored.storage_key, content_type=stored.content_type, size_bytes=stored.size_bytes, sha256=stored.sha256)
    db.add(image)
    audit.record(db, "property.image_added", "property", prop.id, actor_id=user.id, sha256=stored.sha256)
    db.commit()
    db.refresh(image)
    return image


def add_document(db: Session, prop: Property, user: User, data: bytes, filename: str, document_type: str) -> PropertyDocument:
    stored = get_storage().save(data, DOCUMENT_TYPES, f"documents/{prop.id}")
    document = PropertyDocument(
        property_id=prop.id,
        uploaded_by_id=user.id,
        document_type=document_type,
        original_filename=filename[:255] or "document",
        storage_key=stored.storage_key,
        content_type=stored.content_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
    )
    db.add(document)
    audit.record(db, "property.document_added", "property", prop.id, actor_id=user.id, sha256=stored.sha256, document_type=document_type)
    db.commit()
    db.refresh(document)
    return document


def add_renovation(db: Session, prop: Property, user: User, data: dict) -> PropertyRenovation:
    renovation = PropertyRenovation(property_id=prop.id, **data)
    db.add(renovation)
    audit.record(db, "property.renovation_added", "property", prop.id, actor_id=user.id)
    db.flush()
    db.refresh(prop, ["renovations"])
    twin_service.sync_from_property(db, prop, user.id, ["condition"])
    db.commit()
    db.refresh(renovation)
    return renovation


def submit_verification(db: Session, prop: Property, user: User, notes: str | None) -> PropertyVerificationRequest:
    # The row lock makes "at most one open request per property" hold under concurrent submits.
    db.scalar(select(Property.id).where(Property.id == prop.id).with_for_update())
    open_request = db.scalar(
        select(PropertyVerificationRequest.id).where(PropertyVerificationRequest.property_id == prop.id, PropertyVerificationRequest.status == "pending")
    )
    if open_request:
        raise conflict("verification_already_open", "This property already has an open verification request.")
    has_document = db.scalar(select(PropertyDocument.id).where(PropertyDocument.property_id == prop.id).limit(1))
    if not has_document:
        raise AppError(422, "documents_required", "Upload at least one document before requesting verification.")
    request = PropertyVerificationRequest(property_id=prop.id, requested_by_id=user.id, request_notes=notes)
    prop.verification_status = "pending"
    db.add(request)
    db.flush()
    audit.record(db, "verification.submitted", "verification_request", request.id, actor_id=user.id, property_id=str(prop.id))
    db.commit()
    db.refresh(request)
    return request


def decide_verification(db: Session, request_id: uuid.UUID, reviewer: User, decision: str, notes: str) -> PropertyVerificationRequest:
    request = db.scalar(select(PropertyVerificationRequest).where(PropertyVerificationRequest.id == request_id).with_for_update())
    if request is None:
        raise not_found("Verification request")
    if request.status != "pending":
        raise conflict("verification_already_decided", "This request has already been decided.")
    prop = access.load_property(db, request.property_id)
    if prop.owner_id == reviewer.id or request.requested_by_id == reviewer.id:
        raise AppError(403, "conflict_of_interest", "You cannot review your own property.")
    request.status = decision
    request.reviewed_by_id = reviewer.id
    request.decision_notes = notes
    request.decided_at = utcnow()
    prop.verification_status = "verified" if decision == "approved" else "rejected"
    audit.record(db, f"verification.{decision}", "verification_request", request.id, actor_id=reviewer.id, property_id=str(prop.id))
    notify(db, prop.owner_id, "verification_decision", f"Verification {decision}: {prop.title}", notes, f"/properties/{prop.id}")
    db.commit()
    db.refresh(request)
    return request


def report_property(db: Session, prop: Property, user: User, reason: str) -> PropertyReport:
    report = PropertyReport(property_id=prop.id, reported_by_id=user.id, reason=reason)
    db.add(report)
    db.flush()
    audit.record(db, "property.reported", "property", prop.id, actor_id=user.id, report_id=str(report.id))
    db.commit()
    db.refresh(report)
    return report


def save_favorite(db: Session, user: User, prop: Property) -> None:
    if db.get(SavedProperty, (user.id, prop.id)) is None:
        db.add(SavedProperty(user_id=user.id, property_id=prop.id))
        db.commit()


def remove_favorite(db: Session, user: User, property_id: uuid.UUID) -> None:
    favorite = db.get(SavedProperty, (user.id, property_id))
    if favorite is not None:
        db.delete(favorite)
        db.commit()

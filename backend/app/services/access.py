"""Object-level authorization. Every rule that depends on who owns what lives here."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import forbidden, not_found
from app.models import Property, PropertyVerificationRequest, User

PUBLIC_STATUSES = ("listed", "under_offer")


def is_owner_or_admin(user: User | None, prop: Property) -> bool:
    return user is not None and (prop.owner_id == user.id or user.has_role("admin"))


def is_public(prop: Property) -> bool:
    return prop.listing_status in PUBLIC_STATUSES


def verifier_has_access(db: Session, user: User | None, prop: Property) -> bool:
    if user is None or not user.has_role("verifier"):
        return False
    return db.scalar(select(PropertyVerificationRequest.id).where(PropertyVerificationRequest.property_id == prop.id).limit(1)) is not None


def can_view_full(db: Session, user: User | None, prop: Property) -> bool:
    return is_owner_or_admin(user, prop) or verifier_has_access(db, user, prop)


def load_property(db: Session, property_id: uuid.UUID) -> Property:
    prop = db.get(Property, property_id)
    if prop is None:
        raise not_found("Property")
    return prop


def get_visible(db: Session, property_id: uuid.UUID, user: User | None) -> Property:
    """Hidden records answer 404 rather than 403 so that IDs cannot be probed."""
    prop = load_property(db, property_id)
    if is_public(prop) or can_view_full(db, user, prop):
        return prop
    raise not_found("Property")


def get_managed(db: Session, property_id: uuid.UUID, user: User) -> Property:
    prop = load_property(db, property_id)
    if not is_owner_or_admin(user, prop):
        if is_public(prop) or can_view_full(db, user, prop):
            raise forbidden()
        raise not_found("Property")
    return prop


def get_for_review(db: Session, property_id: uuid.UUID, user: User) -> Property:
    prop = load_property(db, property_id)
    if can_view_full(db, user, prop):
        return prop
    if is_public(prop):
        raise forbidden()
    raise not_found("Property")

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import (
    LISTING_STATUSES,
    Money,
    PROPERTY_CONDITIONS,
    PROPERTY_TYPES,
    VERIFICATION_STATUSES,
    CreatedAt,
    UTCDateTime,
    UpdatedAt,
    UuidPK,
    in_list,
    utcnow,
)


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint(in_list("property_type", PROPERTY_TYPES), name="ck_properties_type"),
        CheckConstraint(in_list("listing_status", LISTING_STATUSES), name="ck_properties_listing_status"),
        CheckConstraint(in_list("verification_status", VERIFICATION_STATUSES), name="ck_properties_verification_status"),
        CheckConstraint("`condition` IS NULL OR " + in_list("`condition`", PROPERTY_CONDITIONS), name="ck_properties_condition"),
        CheckConstraint("built_up_area_sqft IS NULL OR built_up_area_sqft > 0", name="ck_properties_area_positive"),
        CheckConstraint("land_area_sqft IS NULL OR land_area_sqft > 0", name="ck_properties_land_positive"),
        CheckConstraint("bedrooms IS NULL OR bedrooms >= 0", name="ck_properties_bedrooms_nonnegative"),
        CheckConstraint("bathrooms IS NULL OR bathrooms >= 0", name="ck_properties_bathrooms_nonnegative"),
        CheckConstraint("parking_spaces >= 0", name="ck_properties_parking_nonnegative"),
        CheckConstraint("last_sale_price IS NULL OR last_sale_price > 0", name="ck_properties_sale_positive"),
        CheckConstraint("asking_price IS NULL OR asking_price > 0", name="ck_properties_asking_positive"),
        CheckConstraint("monthly_rent IS NULL OR monthly_rent >= 0", name="ck_properties_rent_nonnegative"),
        Index("ix_properties_city_type_status", "city", "property_type", "listing_status"),
        Index("ix_properties_status_price", "listing_status", "asking_price"),
        Index("ix_properties_status_area", "listing_status", "built_up_area_sqft"),
    )

    id: Mapped[UuidPK]
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    property_type: Mapped[str] = mapped_column(String(40), nullable=False)
    address_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    locality: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6))
    built_up_area_sqft: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    land_area_sqft: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    bedrooms: Mapped[Optional[int]] = mapped_column(Integer)
    bathrooms: Mapped[Optional[int]] = mapped_column(Integer)
    construction_year: Mapped[Optional[int]] = mapped_column(Integer)
    floor_number: Mapped[Optional[int]] = mapped_column(Integer)
    total_floors: Mapped[Optional[int]] = mapped_column(Integer)
    condition: Mapped[Optional[str]] = mapped_column("condition", String(30))
    amenities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    parking_spaces: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sale_price: Mapped[Optional[Decimal]] = mapped_column(Money)
    last_sale_date: Mapped[Optional[date]] = mapped_column(Date)
    asking_price: Mapped[Optional[Decimal]] = mapped_column(Money)
    monthly_rent: Mapped[Optional[Decimal]] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    listing_status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    owner: Mapped["User"] = relationship(back_populates="properties")  # noqa: F821
    images: Mapped[list["PropertyImage"]] = relationship(back_populates="property", order_by="PropertyImage.created_at")
    renovations: Mapped[list["PropertyRenovation"]] = relationship(back_populates="property", order_by="PropertyRenovation.completed_on")

    @property
    def property_age(self) -> Optional[int]:
        if self.construction_year is None:
            return None
        return max(0, utcnow().year - self.construction_year)


class PropertyImage(Base):
    __tablename__ = "property_images"

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]

    property: Mapped[Property] = relationship(back_populates="images")


class PropertyDocument(Base):
    __tablename__ = "property_documents"

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[CreatedAt]


class PropertyRenovation(Base):
    __tablename__ = "property_renovations"
    __table_args__ = (CheckConstraint("cost IS NULL OR cost >= 0", name="ck_renovations_cost_nonnegative"),)

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    cost: Mapped[Optional[Decimal]] = mapped_column(Money)
    completed_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[CreatedAt]

    property: Mapped[Property] = relationship(back_populates="renovations")


class PropertyVerificationRequest(Base):
    __tablename__ = "property_verification_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_verification_status"),
        Index("ix_verification_status_created", "status", "created_at"),
    )

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    request_notes: Mapped[Optional[str]] = mapped_column(Text)
    decision_notes: Mapped[Optional[str]] = mapped_column(Text)
    decided_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]


class PropertyOwnershipHistory(Base):
    """Application-level record. It is not a legal title register."""

    __tablename__ = "property_ownership_history"

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]


class PropertyReport(Base):
    __tablename__ = "property_reports"
    __table_args__ = (CheckConstraint("status IN ('open', 'dismissed', 'actioned')", name="ck_reports_status"),)

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False, index=True)
    reported_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    resolved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class SavedProperty(Base):
    __tablename__ = "saved_properties"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[CreatedAt]

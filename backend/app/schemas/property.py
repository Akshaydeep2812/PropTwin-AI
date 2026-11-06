import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PropertyType = Literal["apartment", "house", "villa", "townhouse", "plot", "commercial"]
Condition = Literal["poor", "fair", "good", "very_good", "excellent"]
OwnerListingStatus = Literal["draft", "listed", "under_offer", "sold", "archived"]
CURRENT_YEAR_LIMIT = date.today().year + 5
POSTAL_PATTERN = r"^[A-Za-z0-9 \-]+$"


class _PropertyRules(BaseModel):
    @field_validator("amenities", check_fields=False)
    @classmethod
    def clean_amenities(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = sorted({item.strip().lower() for item in value if item.strip()})
        if any(len(item) > 50 for item in cleaned):
            raise ValueError("Each amenity must be 50 characters or fewer.")
        return cleaned

    @model_validator(mode="after")
    def check_floors(self):
        floor, total = getattr(self, "floor_number", None), getattr(self, "total_floors", None)
        if floor is not None and total is not None and floor > total:
            raise ValueError("Floor number cannot be greater than total floors.")
        return self


class PropertyCreate(_PropertyRules):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    property_type: PropertyType
    address_line1: str = Field(min_length=1, max_length=200)
    locality: str | None = Field(default=None, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20, pattern=POSTAL_PATTERN)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    built_up_area_sqft: Decimal | None = Field(default=None, gt=0, le=10000000, decimal_places=2)
    land_area_sqft: Decimal | None = Field(default=None, gt=0, le=100000000, decimal_places=2)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    construction_year: int | None = Field(default=None, ge=1800, le=CURRENT_YEAR_LIMIT)
    floor_number: int | None = Field(default=None, ge=-5, le=300)
    total_floors: int | None = Field(default=None, ge=1, le=300)
    condition: Condition | None = None
    amenities: list[str] = Field(default_factory=list, max_length=50)
    parking_spaces: int = Field(default=0, ge=0, le=1000)
    last_sale_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    last_sale_date: date | None = None
    asking_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    monthly_rent: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    listing_status: Literal["draft", "listed"] = "draft"


class PropertyUpdate(_PropertyRules):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    property_type: PropertyType | None = None
    address_line1: str | None = Field(default=None, min_length=1, max_length=200)
    locality: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20, pattern=POSTAL_PATTERN)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90, decimal_places=6)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180, decimal_places=6)
    built_up_area_sqft: Decimal | None = Field(default=None, gt=0, le=10000000, decimal_places=2)
    land_area_sqft: Decimal | None = Field(default=None, gt=0, le=100000000, decimal_places=2)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    construction_year: int | None = Field(default=None, ge=1800, le=CURRENT_YEAR_LIMIT)
    floor_number: int | None = Field(default=None, ge=-5, le=300)
    total_floors: int | None = Field(default=None, ge=1, le=300)
    condition: Condition | None = None
    amenities: list[str] | None = Field(default=None, max_length=50)
    parking_spaces: int | None = Field(default=None, ge=0, le=1000)
    last_sale_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    last_sale_date: date | None = None
    asking_price: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    monthly_rent: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    listing_status: OwnerListingStatus | None = None

    @model_validator(mode="after")
    def reject_null_for_required_fields(self) -> "PropertyUpdate":
        required = {"title", "property_type", "address_line1", "city", "state", "postal_code", "listing_status", "amenities", "parking_spaces"}
        null_fields = [name for name in required if name in self.model_fields_set and getattr(self, name) is None]
        if null_fields:
            raise ValueError(f"These fields cannot be null: {', '.join(sorted(null_fields))}.")
        return self


class RenovationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=3, max_length=500)
    cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    completed_on: date

    @field_validator("completed_on")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Completion date cannot be in the future.")
        return value


class RenovationRead(BaseModel):
    id: uuid.UUID
    description: str
    cost: Decimal | None
    completed_on: date
    model_config = ConfigDict(from_attributes=True)


class ImageRead(BaseModel):
    id: uuid.UUID
    content_type: str
    size_bytes: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: uuid.UUID
    document_type: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PropertyPublicRead(BaseModel):
    """Safe for anonymous visitors: no street address, exact coordinates, owner, or sale history."""

    id: uuid.UUID
    title: str
    description: str | None
    property_type: str
    locality: str | None
    city: str
    state: str
    built_up_area_sqft: Decimal | None
    land_area_sqft: Decimal | None
    bedrooms: int | None
    bathrooms: int | None
    construction_year: int | None
    property_age: int | None
    floor_number: int | None
    total_floors: int | None
    condition: str | None
    amenities: list[str]
    parking_spaces: int
    asking_price: Decimal | None
    monthly_rent: Decimal | None
    currency: str
    listing_status: str
    verification_status: str
    is_demo: bool
    images: list[ImageRead] = []
    renovations: list[RenovationRead] = []
    created_at: datetime
    updated_at: datetime
    access_level: Literal["public"] = "public"
    model_config = ConfigDict(from_attributes=True)


class PropertyRead(PropertyPublicRead):
    owner_id: uuid.UUID
    address_line1: str
    postal_code: str
    latitude: Decimal | None
    longitude: Decimal | None
    last_sale_price: Decimal | None
    last_sale_date: date | None
    access_level: Literal["full"] = "full"


class VerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=2000)


class VerificationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected"]
    notes: str = Field(min_length=3, max_length=2000)


class VerificationRead(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    property_title: str | None = None
    requested_by_id: uuid.UUID
    reviewed_by_id: uuid.UUID | None
    status: str
    request_notes: str | None
    decision_notes: str | None
    decided_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=5, max_length=1000)


class ReportRead(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    reported_by_id: uuid.UUID
    reason: str
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReportResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["dismissed", "actioned"]
    archive_listing: bool = False

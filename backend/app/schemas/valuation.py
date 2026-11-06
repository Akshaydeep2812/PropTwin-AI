import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.property import Condition, PropertyType


class ValuationFeatures(BaseModel):
    """Inline inputs for valuing a property that is not registered."""

    model_config = ConfigDict(extra="forbid")

    property_type: PropertyType
    built_up_area_sqft: Decimal = Field(gt=0, le=10000000)
    locality: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    land_area_sqft: Decimal | None = Field(default=None, gt=0, le=100000000)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    construction_year: int | None = Field(default=None, ge=1800, le=2100)
    floor_number: int | None = Field(default=None, ge=-5, le=300)
    total_floors: int | None = Field(default=None, ge=1, le=300)
    condition: Condition | None = None
    amenities: list[str] = Field(default_factory=list, max_length=50)
    parking_spaces: int | None = Field(default=None, ge=0, le=1000)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)


class ValuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    property_id: uuid.UUID | None = None
    features: ValuationFeatures | None = None

    @model_validator(mode="after")
    def exactly_one_input(self) -> "ValuationRequest":
        if (self.property_id is None) == (self.features is None):
            raise ValueError("Provide exactly one of property_id or features.")
        return self


class BatchValuationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ValuationRequest] = Field(min_length=1, max_length=50)


class IntervalRead(BaseModel):
    lower: Decimal
    upper: Decimal
    nominal_coverage: Decimal
    method: str = "split_conformal"


class HistoricalComparison(BaseModel):
    previous_value: Decimal | None = None
    previous_valued_at: datetime | None = None
    change_from_previous_pct: Decimal | None = None
    last_sale_price: Decimal | None = None
    last_sale_date: str | None = None


class ValuationRead(BaseModel):
    kind: Literal["ai_estimate"] = "ai_estimate"
    id: uuid.UUID
    property_id: uuid.UUID | None
    predicted_value: Decimal
    currency: str
    interval: IntervalRead | None
    predicted_at: datetime
    model_version: str
    input_summary: dict
    factors: list[dict]
    historical_comparison: HistoricalComparison
    trained_on_synthetic_data: bool
    limitations: list[str]
    disclaimer: str


class ValuationHistoryItem(BaseModel):
    """Enough to draw a trend. Inputs are left out because a visitor may not be entitled to them."""

    kind: Literal["ai_estimate"] = "ai_estimate"
    id: uuid.UUID
    predicted_value: Decimal
    interval_lower: Decimal | None
    interval_upper: Decimal | None
    currency: str
    predicted_at: datetime
    model_version: str
    trained_on_synthetic_data: bool


class ModelVersionRead(BaseModel):
    version: str
    status: str
    beats_baseline: bool
    trained_on_synthetic_data: bool
    trained_at: datetime
    approved_at: datetime | None
    headline_metrics: dict


class ModelMetricsRead(BaseModel):
    version: str
    status: str
    metrics: dict


class ModelPromotion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["approved", "active", "rejected", "retired"]

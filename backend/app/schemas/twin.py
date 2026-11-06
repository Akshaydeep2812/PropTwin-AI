import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.property import Condition


class TwinRead(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    version: int
    state: dict
    current_estimated_value: Decimal | None
    last_valuation_at: datetime | None
    annual_maintenance_cost: Decimal | None
    market_index: Decimal | None
    last_synced_at: datetime
    valuation_is_stale: bool
    twin_type: str
    created_at: datetime
    updated_at: datetime


class TwinUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annual_maintenance_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    maintenance_notes: str | None = Field(default=None, max_length=2000)


class SnapshotRead(BaseModel):
    id: uuid.UUID
    version: int
    state: dict
    estimated_value: Decimal | None
    reason: str
    changed_fields: list
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Scenario", min_length=1, max_length=120)
    market_change_pct: Decimal = Field(default=Decimal("0"), ge=-90, le=200, decimal_places=4)
    renovation_value_uplift_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=4)
    renovation_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    condition_after: Condition | None = None
    monthly_rent_change_pct: Decimal = Field(default=Decimal("0"), ge=-100, le=200, decimal_places=4)
    annual_maintenance_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    maintenance_change_pct: Decimal = Field(default=Decimal("0"), ge=-100, le=500, decimal_places=4)

    @model_validator(mode="after")
    def uplift_and_rerun_are_exclusive(self) -> "SimulationRequest":
        # Both describe the effect of renovation, so applying both would count it twice.
        if self.condition_after is not None and self.renovation_value_uplift_pct != 0:
            raise ValueError("Use either condition_after or renovation_value_uplift_pct, not both.")
        return self


class AssumptionRead(BaseModel):
    name: str
    value: str
    unit: str
    model_config = ConfigDict(from_attributes=True)


class SimulationRead(BaseModel):
    kind: Literal["hypothetical_simulation"] = "hypothetical_simulation"
    id: uuid.UUID
    twin_id: uuid.UUID
    twin_version: int
    name: str
    method: str
    calculation_note: str
    baseline_value: Decimal
    scenario_value: Decimal
    absolute_difference: Decimal
    percentage_difference: Decimal
    annual_rental_income: Decimal | None
    rental_yield_pct: Decimal | None
    annual_maintenance_cost: Decimal | None
    limitations: list[str]
    assumptions: list[AssumptionRead]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class MarketPoint(BaseModel):
    period: str
    price_index: Decimal
    is_synthetic: bool

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.insights import OnboardingRead


class DashboardValuation(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID | None
    property_title: str | None
    predicted_value: Decimal
    currency: str
    predicted_at: datetime
    model_version: str


class DashboardSimulation(BaseModel):
    id: uuid.UUID
    twin_id: uuid.UUID
    name: str
    method: str
    baseline_value: Decimal
    scenario_value: Decimal
    percentage_difference: Decimal
    created_at: datetime


class DashboardTransaction(BaseModel):
    id: uuid.UUID
    property_id: uuid.UUID
    operation: str
    status: str
    tx_hash: str | None
    created_at: datetime


class ModelStatus(BaseModel):
    available: bool
    version: str | None
    trained_on_synthetic_data: bool | None
    trained_at: datetime | None


class DataFreshness(BaseModel):
    latest_market_period: date | None
    market_data_is_synthetic: bool | None
    last_valuation_at: datetime | None


class DashboardRead(BaseModel):
    roles: list[str]
    properties_accessible: int
    active_twins: int
    pending_verifications: int
    saved_properties: int
    latest_valuations: list[DashboardValuation]
    valuation_trend: list[DashboardValuation]
    recent_simulations: list[DashboardSimulation]
    recent_transactions: list[DashboardTransaction]
    model: ModelStatus
    onboarding: OnboardingRead
    data_freshness: DataFreshness


class JobStatusCount(BaseModel):
    status: str
    count: int


class MonitoringRead(BaseModel):
    prediction: dict
    jobs: list[JobStatusCount]
    dead_jobs: list[dict]
    transactions: list[JobStatusCount]
    blockchain: dict
    users: int
    properties: int

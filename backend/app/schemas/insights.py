import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class LocalitySummary(BaseModel):
    locality: str
    city: str
    latest_period: date
    price_index: Decimal
    price_per_sqft: Decimal | None
    monthly_rent_per_sqft: Decimal | None
    gross_yield_pct: Decimal | None
    change_12m_pct: Decimal | None
    cagr_5y_pct: Decimal | None
    active_listings: int
    is_synthetic: bool
    source: str


class MarketOverview(BaseModel):
    localities: list[LocalitySummary]
    cities: list[str]
    latest_period: date | None
    any_synthetic: bool


class MarketTrendPoint(BaseModel):
    period: date
    price_index: Decimal
    price_per_sqft: Decimal | None
    is_synthetic: bool


class InsightMarket(BaseModel):
    locality: str
    latest_period: date
    change_12m_pct: Decimal | None
    cagr_5y_pct: Decimal | None
    is_synthetic: bool


class InsightEstimate(BaseModel):
    value: Decimal
    lower: Decimal | None
    upper: Decimal | None
    predicted_at: datetime
    model_version: str
    trained_on_synthetic_data: bool
    is_current: bool


class InsightStatus(BaseModel):
    has_estimate: bool
    estimate_current: bool
    has_twin: bool
    verification_status: str
    on_chain: bool


class Takeaway(BaseModel):
    tone: Literal["positive", "caution", "neutral"]
    text: str


class Completeness(BaseModel):
    percent: int
    missing: list[str]


class PropertyInsights(BaseModel):
    property_id: uuid.UUID
    currency: str
    asking_price: Decimal | None
    asking_per_sqft: Decimal | None
    market_per_sqft: Decimal | None
    premium_to_market_pct: Decimal | None
    gross_yield_pct: Decimal | None
    market_yield_pct: Decimal | None
    market: InsightMarket | None
    estimate: InsightEstimate | None
    price_position: Literal["below_range", "within_range", "above_range"] | None
    asking_vs_estimate_pct: Decimal | None
    status: InsightStatus
    takeaways: list[Takeaway]
    completeness: Completeness | None
    disclaimer: str


class NextAction(BaseModel):
    label: str
    href: str
    reason: str


class PortfolioRow(BaseModel):
    id: uuid.UUID
    title: str
    locality: str | None
    city: str
    property_type: str
    currency: str
    listing_status: str
    verification_status: str
    asking_price: Decimal | None
    monthly_rent: Decimal | None
    estimate: Decimal | None
    estimate_current: bool
    asking_vs_estimate_pct: Decimal | None
    price_position: str | None
    gross_yield_pct: Decimal | None
    has_twin: bool
    on_chain: bool
    is_demo: bool
    next_action: NextAction | None


class PortfolioRead(BaseModel):
    items: list[PortfolioRow]
    total_properties: int
    truncated: bool
    currency: str | None
    total_estimate: Decimal | None
    total_annual_rent: Decimal | None
    estimated_count: int
    verified_count: int
    twin_count: int
    on_chain_count: int
    action_count: int


class OnboardingStep(BaseModel):
    key: str
    title: str
    description: str
    done: bool
    href: str
    cta: str


class OnboardingRead(BaseModel):
    role: str
    steps: list[OnboardingStep]
    completed: int
    total: int

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import MODEL_STATUSES, SIMULATION_METHODS, CreatedAt, Money, UTCDateTime, UpdatedAt, UuidPK, in_list


class ValuationModelVersion(Base):
    __tablename__ = "valuation_model_versions"
    __table_args__ = (CheckConstraint(in_list("status", MODEL_STATUSES), name="ck_model_status"),)

    id: Mapped[UuidPK]
    version: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="candidate", nullable=False, index=True)
    artifact_path: Mapped[str] = mapped_column(String(500), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    beats_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trained_on_synthetic_data: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trained_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    created_at: Mapped[CreatedAt]


class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (
        CheckConstraint("predicted_value > 0", name="ck_valuations_positive"),
        Index("ix_valuations_property_created", "property_id", "created_at"),
    )

    id: Mapped[UuidPK]
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"))
    requested_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    model_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("valuation_model_versions.id", ondelete="RESTRICT"), nullable=False)
    predicted_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    interval_lower: Mapped[Optional[Decimal]] = mapped_column(Money)
    interval_upper: Mapped[Optional[Decimal]] = mapped_column(Money)
    interval_coverage: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 3))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    input_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    factors: Mapped[list] = mapped_column(JSON, nullable=False)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="user_request", nullable=False)
    created_at: Mapped[CreatedAt]

    model_version: Mapped[ValuationModelVersion] = relationship(lazy="joined")


class DigitalTwin(Base):
    __tablename__ = "digital_twins"

    id: Mapped[UuidPK]
    property_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("properties.id", ondelete="RESTRICT"), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_estimated_value: Mapped[Optional[Decimal]] = mapped_column(Money)
    last_valuation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("valuations.id", ondelete="RESTRICT"))
    last_valuation_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    annual_maintenance_cost: Mapped[Optional[Decimal]] = mapped_column(Money)
    market_index: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    last_synced_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class DigitalTwinSnapshot(Base):
    """Append-only. Rows are never updated or deleted by the application."""

    __tablename__ = "digital_twin_snapshots"
    __table_args__ = (UniqueConstraint("twin_id", "version", name="uq_twin_snapshot_version"),)

    id: Mapped[UuidPK]
    twin_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("digital_twins.id", ondelete="RESTRICT"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    state: Mapped[dict] = mapped_column(JSON, nullable=False)
    estimated_value: Mapped[Optional[Decimal]] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(String(60), nullable=False)
    changed_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[CreatedAt]


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint(in_list("method", SIMULATION_METHODS), name="ck_simulation_method"),
        Index("ix_simulation_twin_created", "twin_id", "created_at"),
    )

    id: Mapped[UuidPK]
    twin_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("digital_twins.id", ondelete="RESTRICT"), nullable=False)
    twin_version: Mapped[int] = mapped_column(nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    calculation_note: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    scenario_value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    absolute_difference: Mapped[Decimal] = mapped_column(Money, nullable=False)
    percentage_difference: Mapped[Decimal] = mapped_column(Numeric(9, 4), nullable=False)
    annual_rental_income: Mapped[Optional[Decimal]] = mapped_column(Money)
    rental_yield_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 4))
    annual_maintenance_cost: Mapped[Optional[Decimal]] = mapped_column(Money)
    limitations: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[CreatedAt]

    assumptions: Mapped[list["SimulationAssumption"]] = relationship(lazy="selectin", order_by="SimulationAssumption.name")


class SimulationAssumption(Base):
    __tablename__ = "simulation_assumptions"
    __table_args__ = (UniqueConstraint("simulation_id", "name", name="uq_simulation_assumption"),)

    id: Mapped[UuidPK]
    simulation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("simulation_runs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    value: Mapped[str] = mapped_column(String(60), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)


class MarketObservation(Base):
    __tablename__ = "market_observations"
    __table_args__ = (UniqueConstraint("locality", "period", "source", name="uq_market_observation"),)

    id: Mapped[UuidPK]
    locality: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    price_index: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    median_price_per_sqft: Mapped[Optional[Decimal]] = mapped_column(Money)
    median_monthly_rent_per_sqft: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[CreatedAt]

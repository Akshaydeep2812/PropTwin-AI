import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, Numeric, TypeDecorator, Uuid
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import mapped_column


class UTCDateTime(TypeDecorator):
    """Stores naive UTC (MySQL DATETIME has no zone) and always returns aware UTC values."""

    impl = DateTime(timezone=False)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        # MySQL's default DATETIME keeps whole seconds, which would make same-second events unorderable.
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime(timezone=False))

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not accepted; use an aware UTC datetime.")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


Money = Numeric(18, 2)
UuidPK = Annotated[uuid.UUID, mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)]
CreatedAt = Annotated[datetime, mapped_column(UTCDateTime, default=utcnow, nullable=False)]
UpdatedAt = Annotated[datetime, mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)]
MoneyValue = Decimal

PROPERTY_TYPES = ("apartment", "house", "villa", "townhouse", "plot", "commercial")
PROPERTY_CONDITIONS = ("poor", "fair", "good", "very_good", "excellent")
LISTING_STATUSES = ("draft", "listed", "under_offer", "sold", "archived")
VERIFICATION_STATUSES = ("unverified", "pending", "verified", "rejected")
ROLE_NAMES = ("owner", "investor", "verifier", "admin")
MODEL_STATUSES = ("candidate", "approved", "active", "retired", "rejected")
TX_STATUSES = ("pending", "submitted", "confirmed", "failed", "reverted")
TX_OPERATIONS = ("register", "update", "propose_transfer", "accept_transfer", "cancel_transfer", "commit_valuation")
TRANSFER_STATUSES = ("requested", "proposed", "accepted", "cancelled", "failed")
JOB_STATUSES = ("queued", "running", "succeeded", "dead")
SIMULATION_METHODS = ("formula", "model_rerun")


def in_list(column: str, values: tuple[str, ...]) -> str:
    """Builds the SQL for a CHECK constraint from a fixed internal tuple, never from user input."""
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"

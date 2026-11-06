"""Twin state helpers shared by the twin and valuation services. Snapshots are only ever inserted here."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DigitalTwin, DigitalTwinSnapshot, Property, Valuation
from app.models.types import utcnow

# Street address and exact coordinates stay out so that a twin can be shown to investors on listed properties.
STATE_FIELDS = (
    "property_type", "locality", "city", "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year",
    "floor_number", "total_floors", "condition", "amenities", "parking_spaces", "monthly_rent", "listing_status", "verification_status",
)
TRACKED_FIELDS = frozenset(STATE_FIELDS)


def _json_safe(value: Any) -> Any:
    return str(value) if isinstance(value, Decimal) else value


def build_state(prop: Property, operating: dict | None = None) -> dict:
    state = {field: _json_safe(getattr(prop, field)) for field in STATE_FIELDS}
    state["renovations"] = [
        {"description": item.description, "cost": _json_safe(item.cost), "completed_on": item.completed_on.isoformat()} for item in prop.renovations
    ]
    state["operating"] = operating or {}
    return state


def write_snapshot(db: Session, twin: DigitalTwin, reason: str, changed_fields: list[str], actor_id: uuid.UUID | None) -> DigitalTwinSnapshot:
    snapshot = DigitalTwinSnapshot(
        twin_id=twin.id,
        version=twin.version,
        state=twin.state,
        estimated_value=twin.current_estimated_value,
        reason=reason,
        changed_fields=changed_fields,
        actor_id=actor_id,
    )
    db.add(snapshot)
    return snapshot


def lock_twin_for_property(db: Session, property_id: uuid.UUID) -> DigitalTwin | None:
    return db.scalar(select(DigitalTwin).where(DigitalTwin.property_id == property_id).with_for_update())


def apply_valuation(db: Session, valuation: Valuation, actor_id: uuid.UUID | None) -> None:
    """Records a new estimate on the property's twin, if it has one, as a new version."""
    if valuation.property_id is None:
        return
    twin = lock_twin_for_property(db, valuation.property_id)
    if twin is None:
        return
    twin.version += 1
    twin.current_estimated_value = valuation.predicted_value
    twin.last_valuation_id = valuation.id
    twin.last_valuation_at = utcnow()
    write_snapshot(db, twin, "revaluation", ["current_estimated_value"], actor_id)

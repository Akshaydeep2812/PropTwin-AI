import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError, conflict, forbidden, not_found
from app.models import DigitalTwin, DigitalTwinSnapshot, MarketObservation, Property, SimulationAssumption, SimulationRun, User, Valuation
from app.models.types import utcnow
from app.services import access, audit, jobs, simulation, twin_state, valuation_service

TWIN_KIND_NOTE = "Software-based digital twin driven by periodic updates and simulated events. It has no live sensor feed."
SIMULATION_LIMITATIONS = [
    "This is a hypothetical calculation from the stated assumptions, not a forecast of what will happen.",
    "It does not include taxes, transaction costs, financing, or vacancy.",
]


def _latest_valuation(db: Session, property_id: uuid.UUID) -> Valuation | None:
    return db.scalar(select(Valuation).where(Valuation.property_id == property_id).order_by(Valuation.created_at.desc()).limit(1))


def create_twin(db: Session, prop: Property, user: User) -> DigitalTwin:
    if db.scalar(select(DigitalTwin.id).where(DigitalTwin.property_id == prop.id)):
        raise conflict("twin_exists", "This property already has a digital twin.")
    valuation = _latest_valuation(db, prop.id)
    if valuation is None:
        try:
            valuation = valuation_service.value_property(db, prop, user, source="twin_create")
        except AppError as exc:
            # A twin is still useful without a model or an area. It reports having no estimate rather than inventing one.
            if exc.code not in ("model_unavailable", "insufficient_features", "estimate_out_of_range"):
                raise
    # An estimate is current if the property has not changed since it was made; older ones show as stale.
    is_current = valuation is not None and prop.updated_at <= valuation.created_at
    twin = DigitalTwin(
        property_id=prop.id,
        version=1,
        state=twin_state.build_state(prop),
        current_estimated_value=None if valuation is None else valuation.predicted_value,
        last_valuation_id=None if valuation is None else valuation.id,
        last_valuation_at=None if valuation is None else valuation.created_at,
        market_index=_market_index(db, prop.locality),
        last_synced_at=valuation.created_at if is_current else utcnow(),
    )
    db.add(twin)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("twin_exists", "This property already has a digital twin.") from exc
    twin_state.write_snapshot(db, twin, "created", [], user.id)
    audit.record(db, "twin.created", "digital_twin", twin.id, actor_id=user.id, property_id=str(prop.id))
    db.commit()
    db.refresh(twin)
    return twin


def _market_index(db: Session, locality: str | None) -> Decimal | None:
    value = valuation_service.latest_market_index(db, locality)
    return None if value is None else Decimal(str(value))


def sync_from_property(db: Session, prop: Property, actor_id: uuid.UUID | None, changed_fields: list[str]) -> None:
    """Runs inside the caller's transaction, so a property change and its snapshot commit or roll back together."""
    relevant = sorted(set(changed_fields) & twin_state.TRACKED_FIELDS)
    if not relevant:
        return
    twin = twin_state.lock_twin_for_property(db, prop.id)
    if twin is None:
        return
    twin.version += 1
    twin.state = twin_state.build_state(prop, twin.state.get("operating"))
    twin.market_index = _market_index(db, prop.locality)
    twin.last_synced_at = utcnow()
    twin_state.write_snapshot(db, twin, "property_sync", relevant, actor_id)
    audit.record(db, "twin.synced", "digital_twin", twin.id, actor_id=actor_id, fields=relevant)
    # Revaluation can fail or wait for a model, so it is a retried job rather than part of this transaction.
    jobs.enqueue(db, "twin_revalue", {"property_id": str(prop.id)})


def revalue(db: Session, property_id: uuid.UUID) -> None:
    prop = db.get(Property, property_id)
    if prop is None:
        return
    try:
        valuation_service.value_property(db, prop, None, source="twin_sync")
    except AppError as exc:
        # With no model or usable inputs, retrying cannot help. The twin stays visibly stale until it can be valued.
        if exc.code in ("model_unavailable", "insufficient_features", "estimate_out_of_range"):
            return
        raise


def update_operating(db: Session, twin: DigitalTwin, user: User, changes: dict[str, Any]) -> DigitalTwin:
    db.scalar(select(DigitalTwin.id).where(DigitalTwin.id == twin.id).with_for_update())
    operating = dict(twin.state.get("operating") or {})
    changed = []
    if "annual_maintenance_cost" in changes:
        twin.annual_maintenance_cost = changes["annual_maintenance_cost"]
        operating["annual_maintenance_cost"] = None if changes["annual_maintenance_cost"] is None else str(changes["annual_maintenance_cost"])
        changed.append("annual_maintenance_cost")
    if "maintenance_notes" in changes:
        operating["maintenance_notes"] = changes["maintenance_notes"]
        changed.append("maintenance_notes")
    if not changed:
        return twin
    twin.version += 1
    twin.state = {**twin.state, "operating": operating}
    twin.last_synced_at = utcnow()
    twin_state.write_snapshot(db, twin, "operating_update", changed, user.id)
    audit.record(db, "twin.updated", "digital_twin", twin.id, actor_id=user.id, fields=changed)
    db.commit()
    db.refresh(twin)
    return twin


def get_twin(db: Session, twin_id: uuid.UUID) -> tuple[DigitalTwin, Property]:
    twin = db.get(DigitalTwin, twin_id)
    if twin is None:
        raise not_found("Digital twin")
    return twin, access.load_property(db, twin.property_id)


def get_for_viewer(db: Session, twin_id: uuid.UUID, user: User) -> tuple[DigitalTwin, Property]:
    twin, prop = get_twin(db, twin_id)
    if access.can_view_full(db, user, prop) or (access.is_public(prop) and user.has_role("investor")):
        return twin, prop
    raise not_found("Digital twin")


def get_for_manager(db: Session, twin_id: uuid.UUID, user: User) -> tuple[DigitalTwin, Property]:
    twin, prop = get_for_viewer(db, twin_id, user)
    if not access.is_owner_or_admin(user, prop):
        raise forbidden()
    return twin, prop


def get_by_property(db: Session, property_id: uuid.UUID, user: User) -> DigitalTwin:
    prop = access.load_property(db, property_id)
    if not (access.can_view_full(db, user, prop) or (access.is_public(prop) and user.has_role("investor"))):
        raise not_found("Digital twin")
    twin = db.scalar(select(DigitalTwin).where(DigitalTwin.property_id == prop.id))
    if twin is None:
        raise not_found("Digital twin")
    return twin


def serialize(twin: DigitalTwin) -> dict:
    return {
        "id": twin.id,
        "property_id": twin.property_id,
        "version": twin.version,
        "state": twin.state,
        "current_estimated_value": twin.current_estimated_value,
        "last_valuation_at": twin.last_valuation_at,
        "annual_maintenance_cost": twin.annual_maintenance_cost,
        "market_index": twin.market_index,
        "last_synced_at": twin.last_synced_at,
        "valuation_is_stale": twin.last_valuation_at is None or twin.last_synced_at > twin.last_valuation_at,
        "twin_type": TWIN_KIND_NOTE,
        "created_at": twin.created_at,
        "updated_at": twin.updated_at,
    }


def _assumptions(payload: dict) -> list[tuple[str, str, str]]:
    units = {
        "market_change_pct": "percent",
        "renovation_value_uplift_pct": "percent",
        "renovation_cost": "currency",
        "monthly_rent_change_pct": "percent",
        "annual_maintenance_cost": "currency",
        "maintenance_change_pct": "percent",
        "condition_after": "category",
    }
    return [(name, str(payload[name]), unit) for name, unit in units.items() if payload.get(name) is not None]


def simulate(db: Session, twin: DigitalTwin, prop: Property, user: User, name: str, payload: dict) -> SimulationRun:
    baseline = twin.current_estimated_value
    if baseline is None:
        raise AppError(409, "baseline_required", "Value this property first. A scenario needs a baseline estimate to start from.")

    condition_after = payload.get("condition_after")
    adjusted_base = None
    method = "formula"
    if condition_after and condition_after != prop.condition:
        raw = {**valuation_service.property_to_raw(prop), "condition": condition_after}
        adjusted_base = valuation_service.estimate(db, raw)["prediction"].value
        method = "model_rerun"

    maintenance = payload.get("annual_maintenance_cost")
    inputs = simulation.ScenarioInputs(
        baseline_value=baseline,
        market_change_pct=payload["market_change_pct"],
        renovation_value_uplift_pct=payload["renovation_value_uplift_pct"],
        monthly_rent=prop.monthly_rent,
        monthly_rent_change_pct=payload["monthly_rent_change_pct"],
        annual_maintenance_cost=twin.annual_maintenance_cost if maintenance is None else maintenance,
        maintenance_change_pct=payload["maintenance_change_pct"],
    )
    result = simulation.calculate(inputs, adjusted_base)

    if method == "model_rerun":
        note = (
            f"Valuation model rerun with condition '{condition_after}' gave {adjusted_base}. "
            f"Then: value x (1 + market {inputs.market_change_pct}%) x (1 + uplift {inputs.renovation_value_uplift_pct}%)."
        )
    else:
        note = (
            f"Hypothetical arithmetic, not a new model prediction: baseline {baseline} "
            f"x (1 + market {inputs.market_change_pct}%) x (1 + uplift {inputs.renovation_value_uplift_pct}%)."
        )
    limitations = list(SIMULATION_LIMITATIONS)
    if inputs.monthly_rent is None:
        limitations.append("No rent is recorded for this property, so rental income and yield were not calculated.")
    if inputs.annual_maintenance_cost is None:
        limitations.append("No maintenance cost is recorded, so it was not calculated.")

    run = SimulationRun(
        twin_id=twin.id,
        twin_version=twin.version,
        created_by_id=user.id,
        name=name,
        method=method,
        calculation_note=note,
        baseline_value=baseline,
        scenario_value=result.scenario_value,
        absolute_difference=result.absolute_difference,
        percentage_difference=result.percentage_difference,
        annual_rental_income=result.annual_rental_income,
        rental_yield_pct=result.rental_yield_pct,
        annual_maintenance_cost=result.annual_maintenance_cost,
        limitations=limitations,
    )
    db.add(run)
    db.flush()
    for assumption_name, value, unit in _assumptions(payload):
        db.add(SimulationAssumption(simulation_id=run.id, name=assumption_name, value=value, unit=unit))
    audit.record(db, "simulation.created", "simulation_run", run.id, actor_id=user.id, twin_id=str(twin.id), method=method)
    db.commit()
    db.refresh(run)
    return run


def history(db: Session, twin: DigitalTwin, page: int, page_size: int) -> tuple[list[DigitalTwinSnapshot], int]:
    total = db.scalar(select(func.count()).select_from(DigitalTwinSnapshot).where(DigitalTwinSnapshot.twin_id == twin.id)) or 0
    rows = db.scalars(
        select(DigitalTwinSnapshot).where(DigitalTwinSnapshot.twin_id == twin.id).order_by(DigitalTwinSnapshot.version.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows), total


def simulations(db: Session, twin: DigitalTwin, prop: Property, user: User, page: int, page_size: int) -> tuple[list[SimulationRun], int]:
    conditions = [SimulationRun.twin_id == twin.id]
    # An investor's scenarios reveal their interest, so other people's runs stay private to them.
    if not access.is_owner_or_admin(user, prop):
        conditions.append(SimulationRun.created_by_id == user.id)
    total = db.scalar(select(func.count()).select_from(SimulationRun).where(*conditions)) or 0
    rows = db.scalars(select(SimulationRun).where(*conditions).order_by(SimulationRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


def market_series(db: Session, locality: str | None) -> list[MarketObservation]:
    if not locality:
        return []
    return list(db.scalars(select(MarketObservation).where(MarketObservation.locality == locality).order_by(MarketObservation.period)))

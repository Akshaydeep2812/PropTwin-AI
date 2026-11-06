from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJob,
    BlockchainTransaction,
    DigitalTwin,
    MarketObservation,
    Property,
    PropertyVerificationRequest,
    SavedProperty,
    SimulationRun,
    User,
    Valuation,
)
from app.services import access, blockchain_service, onboarding_service, valuation_service

RECENT_LIMIT = 5
TREND_LIMIT = 30


def _count(db: Session, statement) -> int:
    return db.scalar(statement) or 0


def _valuation_row(valuation: Valuation, title: str | None) -> dict:
    return {
        "id": valuation.id,
        "property_id": valuation.property_id,
        "property_title": title,
        "predicted_value": valuation.predicted_value,
        "currency": valuation.currency,
        "predicted_at": valuation.created_at,
        "model_version": valuation.model_version.version,
    }


def build(db: Session, user: User) -> dict:
    is_admin = user.has_role("admin")
    is_verifier = user.has_role("verifier")
    owned = Property.owner_id == user.id

    if is_admin:
        accessible = select(func.count()).select_from(Property)
    elif user.has_role("owner"):
        accessible = select(func.count()).select_from(Property).where(owned, Property.listing_status != "archived")
    else:
        accessible = select(func.count()).select_from(Property).where(Property.listing_status.in_(access.PUBLIC_STATUSES))

    twins = select(func.count()).select_from(DigitalTwin)
    if not is_admin:
        twins = twins.join(Property, Property.id == DigitalTwin.property_id).where(owned)

    pending = select(func.count()).select_from(PropertyVerificationRequest).where(PropertyVerificationRequest.status == "pending")
    if not (is_admin or is_verifier):
        pending = pending.where(PropertyVerificationRequest.requested_by_id == user.id)

    # A user's estimates are those they asked for, plus any made on properties they own.
    valuation_scope = (
        select(Valuation, Property.title)
        .outerjoin(Property, Property.id == Valuation.property_id)
        .where(or_(Valuation.requested_by_id == user.id, owned))
        .order_by(Valuation.created_at.desc())
    )
    valuations = db.execute(valuation_scope.limit(TREND_LIMIT)).all()

    simulations = db.scalars(select(SimulationRun).where(SimulationRun.created_by_id == user.id).order_by(SimulationRun.created_at.desc()).limit(RECENT_LIMIT)).all()

    transactions = select(BlockchainTransaction).order_by(BlockchainTransaction.created_at.desc()).limit(RECENT_LIMIT)
    if not is_admin:
        transactions = transactions.where(BlockchainTransaction.initiated_by_id == user.id)

    latest_market = db.execute(select(MarketObservation.period, MarketObservation.is_synthetic).order_by(MarketObservation.period.desc()).limit(1)).first()

    return {
        "roles": user.role_names,
        "properties_accessible": _count(db, accessible),
        "active_twins": _count(db, twins),
        "pending_verifications": _count(db, pending),
        "saved_properties": _count(db, select(func.count()).select_from(SavedProperty).where(SavedProperty.user_id == user.id)),
        "latest_valuations": [_valuation_row(row, title) for row, title in valuations[:RECENT_LIMIT]],
        "valuation_trend": [_valuation_row(row, title) for row, title in reversed(valuations)],
        "recent_simulations": [
            {
                "id": run.id,
                "twin_id": run.twin_id,
                "name": run.name,
                "method": run.method,
                "baseline_value": run.baseline_value,
                "scenario_value": run.scenario_value,
                "percentage_difference": run.percentage_difference,
                "created_at": run.created_at,
            }
            for run in simulations
        ],
        "recent_transactions": list(db.scalars(transactions)),
        "model": valuation_service.model_status(db),
        "onboarding": onboarding_service.build(db, user),
        "data_freshness": {
            "latest_market_period": None if latest_market is None else latest_market[0],
            "market_data_is_synthetic": None if latest_market is None else latest_market[1],
            "last_valuation_at": valuations[0][0].created_at if valuations else None,
        },
    }


def monitoring(db: Session) -> dict:
    def grouped(column) -> list[dict]:
        return [{"status": status, "count": count} for status, count in db.execute(select(column, func.count()).group_by(column))]

    dead = db.scalars(select(BackgroundJob).where(BackgroundJob.status == "dead").order_by(BackgroundJob.updated_at.desc()).limit(20))
    return {
        "prediction": valuation_service.prediction_monitoring(db),
        "jobs": grouped(BackgroundJob.status),
        "dead_jobs": [{"id": str(job.id), "kind": job.kind, "attempts": job.attempts, "last_error": job.last_error, "updated_at": job.updated_at.isoformat()} for job in dead],
        "transactions": grouped(BlockchainTransaction.status),
        "blockchain": blockchain_service.network_status(),
        "users": _count(db, select(func.count()).select_from(User)),
        "properties": _count(db, select(func.count()).select_from(Property)),
    }

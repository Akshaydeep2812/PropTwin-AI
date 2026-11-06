from uuid import UUID

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.dependencies import AdminUser, CurrentUser, DatabaseSession, OptionalUser, Paging
from app.core.errors import not_found
from app.core.rate_limit import limiter
from app.models import Valuation, ValuationModelVersion
from app.schemas.valuation import (
    BatchValuationRequest,
    ModelMetricsRead,
    ModelPromotion,
    ModelVersionRead,
    ValuationHistoryItem,
    ValuationRead,
    ValuationRequest,
)
from app.services import access, valuation_service

router = APIRouter(prefix="/valuations", tags=["valuations"])
history_router = APIRouter(prefix="/properties", tags=["valuations"])
admin_router = APIRouter(prefix="/admin/models", tags=["administration"])


@router.post("/predict", response_model=ValuationRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def predict(request: Request, payload: ValuationRequest, user: CurrentUser, db: DatabaseSession) -> dict:
    features = None if payload.features is None else payload.features.model_dump()
    valuation = valuation_service.value_request(db, payload.property_id, features, user)
    db.commit()
    db.refresh(valuation)
    return valuation_service.serialize(db, valuation, user)


@router.post("/batch", response_model=list[ValuationRead], status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def predict_batch(request: Request, payload: BatchValuationRequest, user: CurrentUser, db: DatabaseSession) -> list[dict]:
    # One transaction: if any item is not permitted or invalid, nothing is saved.
    valuations = [
        valuation_service.value_request(db, item.property_id, None if item.features is None else item.features.model_dump(), user)
        for item in payload.items
    ]
    db.commit()
    return [valuation_service.serialize(db, valuation, user) for valuation in valuations]


@router.get("/{valuation_id}", response_model=ValuationRead)
def get_valuation(valuation_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    valuation = db.get(Valuation, valuation_id)
    if valuation is None or not valuation_service.can_read(db, valuation, user):
        raise not_found("Valuation")
    return valuation_service.serialize(db, valuation, user)


@history_router.get("/{property_id}/valuations", response_model=list[ValuationHistoryItem])
def property_valuations(property_id: UUID, db: DatabaseSession, user: OptionalUser, paging: Paging) -> list[dict]:
    prop = access.get_visible(db, property_id, user)
    rows = db.scalars(
        select(Valuation)
        .where(Valuation.property_id == prop.id)
        .order_by(Valuation.created_at.desc())
        .offset((paging.page - 1) * paging.page_size)
        .limit(paging.page_size)
    )
    return [
        {
            "id": row.id,
            "predicted_value": row.predicted_value,
            "interval_lower": row.interval_lower,
            "interval_upper": row.interval_upper,
            "currency": row.currency,
            "predicted_at": row.created_at,
            "model_version": row.model_version.version,
            "trained_on_synthetic_data": row.model_version.trained_on_synthetic_data,
        }
        for row in rows
    ]


def _model_read(record: ValuationModelVersion) -> dict:
    return {
        "version": record.version,
        "status": record.status,
        "beats_baseline": record.beats_baseline,
        "trained_on_synthetic_data": record.trained_on_synthetic_data,
        "trained_at": record.trained_at,
        "approved_at": record.approved_at,
        "headline_metrics": record.metrics["held_out_test"]["pytorch_mlp"],
    }


@admin_router.get("", response_model=list[ModelVersionRead])
def list_models(admin: AdminUser, db: DatabaseSession) -> list[dict]:
    valuation_service.sync_artifacts(db)
    records = db.scalars(select(ValuationModelVersion).order_by(ValuationModelVersion.trained_at.desc()))
    return [_model_read(record) for record in records]


@admin_router.get("/{model_version}/metrics", response_model=ModelMetricsRead)
def model_metrics(model_version: str, admin: AdminUser, db: DatabaseSession) -> dict:
    valuation_service.sync_artifacts(db)
    record = valuation_service.get_model_record(db, model_version)
    return {"version": record.version, "status": record.status, "metrics": record.metrics}


@admin_router.post("/{model_version}/promote", response_model=ModelVersionRead)
def promote_model(model_version: str, payload: ModelPromotion, admin: AdminUser, db: DatabaseSession) -> dict:
    return _model_read(valuation_service.promote(db, model_version, payload.target, admin))

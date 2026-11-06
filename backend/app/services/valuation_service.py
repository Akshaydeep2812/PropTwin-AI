import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, conflict, not_found
from app.ml.features import build_feature_row
from app.ml.inference import EstimateOutOfRangeError, LoadedModel, ModelArtifactError, load_cached, population_stability_index, read_manifest, sha256_bytes
from app.models import MarketObservation, Property, User, Valuation, ValuationModelVersion
from app.models.types import utcnow
from app.services import access, audit, twin_state

DISCLAIMER = "Estimated market value from a statistical model. It is not a guaranteed sale price or a certified appraisal."
MODEL_UNAVAILABLE = AppError(503, "model_unavailable", "No approved valuation model is active. No estimate has been produced.")
PSI_MIN_ROWS = 30


def sync_artifacts(db: Session) -> None:
    """Registers any new artifact directory as a candidate. Registering never activates anything."""
    root = get_settings().model_artifact_dir
    if not root.is_dir():
        return
    known = set(db.scalars(select(ValuationModelVersion.version)))
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest["version"] in known:
            continue
        metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        db.add(
            ValuationModelVersion(
                version=manifest["version"],
                artifact_path=directory.name,
                manifest_sha256=sha256_bytes(manifest_bytes),
                metrics=metrics,
                beats_baseline=metrics["beats_baseline"],
                trained_on_synthetic_data=manifest["trained_on_synthetic_data"],
                trained_at=utcnow().fromisoformat(manifest["trained_at"]),
            )
        )
    db.commit()


def get_model_record(db: Session, version: str) -> ValuationModelVersion:
    record = db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.version == version))
    if record is None:
        raise not_found("Model version")
    return record


def promote(db: Session, version: str, target: str, admin: User) -> ValuationModelVersion:
    record = db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.version == version).with_for_update())
    if record is None:
        raise not_found("Model version")
    allowed = {
        "candidate": {"approved", "rejected"},
        "approved": {"active", "rejected"},
        "active": {"retired"},
        "retired": {"approved"},
    }
    if target not in allowed.get(record.status, set()):
        raise conflict("invalid_model_transition", f"A model that is {record.status} cannot become {target}.")
    if target == "approved":
        if not record.beats_baseline:
            raise AppError(422, "failed_baseline_gate", "This model did not beat the best baseline on held-out data, so it cannot be approved.")
        record.approved_by_id, record.approved_at = admin.id, utcnow()
    if target == "active":
        _load(record)  # Refuse activation if the artifact is missing or fails its integrity checks.
        for current in db.scalars(select(ValuationModelVersion).where(ValuationModelVersion.status == "active").with_for_update()):
            current.status = "retired"
    record.status = target
    audit.record(db, f"model.{target}", "model_version", version, actor_id=admin.id)
    db.commit()
    db.refresh(record)
    return record


def _load(record: ValuationModelVersion) -> LoadedModel:
    directory: Path = get_settings().model_artifact_dir / record.artifact_path
    try:
        return load_cached(directory, record.manifest_sha256)
    except (ModelArtifactError, FileNotFoundError, OSError) as exc:
        raise AppError(503, "model_unavailable", "The active model artifact could not be loaded safely.") from exc


def active_model(db: Session) -> tuple[ValuationModelVersion, LoadedModel]:
    record = db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.status == "active"))
    if record is None:
        raise MODEL_UNAVAILABLE
    return record, _load(record)


def model_status(db: Session) -> dict[str, Any]:
    record = db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.status == "active"))
    if record is None:
        return {"available": False, "version": None, "trained_on_synthetic_data": None, "trained_at": None}
    return {"available": True, "version": record.version, "trained_on_synthetic_data": record.trained_on_synthetic_data, "trained_at": record.trained_at}


def latest_market_index(db: Session, locality: str | None) -> float | None:
    if not locality:
        return None
    observation = db.scalar(
        select(MarketObservation)
        .where(MarketObservation.locality == locality, MarketObservation.period <= date.today())
        .order_by(MarketObservation.period.desc())
        .limit(1)
    )
    return None if observation is None else float(observation.price_index)


def _limitations(raw: dict, row: dict, record: ValuationModelVersion, model: LoadedModel) -> list[str]:
    notes = ["The estimate reflects only the listed inputs. It does not account for an inspection, legal status, or negotiation."]
    if record.trained_on_synthetic_data:
        notes.insert(0, "This model was trained on synthetic demo data. The figure demonstrates the software and is not evidence of real market value.")
    ranges = model.manifest["supported_ranges"]
    area = row.get("built_up_area_sqft")
    if area is not None and not ranges["built_up_area_sqft"][0] <= area <= ranges["built_up_area_sqft"][1]:
        notes.append("The built-up area is outside the range the model was trained on, so this estimate is less reliable.")
    if raw.get("locality") not in ranges["localities"]:
        notes.append("The model has no training data for this locality, so location had little usable signal.")
    index = row.get("market_index")
    if index is None:
        notes.append("No market index was available for this locality; a typical value from training was substituted.")
    elif not ranges["market_index"][0] <= index <= ranges["market_index"][1]:
        notes.append("The current market index is outside the range seen in training, so the model is extrapolating.")
    expected = ["condition", "construction_year", "bathrooms"]
    if raw.get("property_type") in ("apartment", "commercial"):
        expected += ["floor_number", "total_floors"]
    if raw.get("property_type") in ("apartment", "house", "villa", "townhouse"):
        expected.append("bedrooms")
    missing = sorted(name for name in expected if raw.get(name) is None)
    if missing:
        notes.append(f"Missing inputs were filled with typical training values, which can move the estimate considerably: {', '.join(missing)}.")
    return notes


def _input_summary(raw: dict) -> dict:
    """Deliberately excludes street address and coordinates, which are stored on the valuation row."""
    keys = ("property_type", "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year", "condition", "locality", "city", "floor_number", "total_floors", "parking_spaces")
    summary = {key: (str(raw[key]) if isinstance(raw.get(key), Decimal) else raw.get(key)) for key in keys}
    summary["amenities"] = sorted(raw.get("amenities") or [])
    return summary


def property_to_raw(prop: Property) -> dict:
    return {
        column: getattr(prop, column)
        for column in (
            "property_type", "built_up_area_sqft", "land_area_sqft", "bedrooms", "bathrooms", "construction_year", "floor_number",
            "total_floors", "condition", "amenities", "parking_spaces", "latitude", "longitude", "locality", "city",
        )
    }


def _same_input(saved, current) -> bool:
    # Stored inputs are JSON, and the same number can come back as "1250", "1250.00" or 1250.
    if saved == current:
        return True
    try:
        return Decimal(str(saved)) == Decimal(str(current))
    except (ArithmeticError, ValueError):
        return False


def inputs_unchanged(valuation: Valuation, prop: Property) -> bool:
    """True while the property still has the inputs this estimate used. Other edits, such as a verification decision or a new description, leave it current."""
    current = _input_summary(property_to_raw(prop))
    saved = valuation.input_summary or {}
    return all(_same_input(saved.get(key), value) for key, value in current.items())


def estimate(db: Session, raw: dict) -> dict:
    """Runs the active model without saving anything. Scenario reruns use this directly."""
    if raw.get("built_up_area_sqft") is None:
        raise AppError(422, "insufficient_features", "Built-up area is required to produce an estimate.")
    record, model = active_model(db)
    market_index = latest_market_index(db, raw.get("locality"))
    row = build_feature_row(raw, date.today(), market_index)
    try:
        prediction = model.predict(row)
    except EstimateOutOfRangeError as exc:
        raise AppError(422, "estimate_out_of_range", "These inputs are too far outside the model's training data to produce a meaningful estimate.") from exc
    return {"record": record, "prediction": prediction, "limitations": _limitations(raw, row, record, model)}


def _create(db: Session, raw: dict, user: User | None, prop: Property | None, source: str) -> Valuation:
    result = estimate(db, raw)
    prediction = result["prediction"]
    valuation = Valuation(
        property_id=None if prop is None else prop.id,
        requested_by_id=None if user is None else user.id,
        model_version_id=result["record"].id,
        predicted_value=prediction.value,
        interval_lower=prediction.lower,
        interval_upper=prediction.upper,
        interval_coverage=Decimal(str(prediction.coverage)),
        currency=prop.currency if prop else get_settings().default_currency,
        input_summary=_input_summary(raw),
        factors=prediction.factors,
        limitations=result["limitations"],
        source=source,
    )
    db.add(valuation)
    db.flush()
    audit.record(db, "valuation.created", "valuation", valuation.id, actor_id=None if user is None else user.id, property_id=None if prop is None else str(prop.id), model_version=result["record"].version)
    return valuation


def value_property(db: Session, prop: Property, user: User | None, source: str = "user_request") -> Valuation:
    valuation = _create(db, property_to_raw(prop), user, prop, source)
    # An interested investor's request is saved, but only the owner or the system moves the twin's state.
    if user is None or access.is_owner_or_admin(user, prop):
        twin_state.apply_valuation(db, valuation, None if user is None else user.id)
    return valuation


def value_request(db: Session, property_id, features: dict | None, user: User) -> Valuation:
    if property_id is not None:
        prop = access.get_visible(db, property_id, user)
        return value_property(db, prop, user)
    return _create(db, features, user, None, "user_request")


def can_read(db: Session, valuation: Valuation, user: User) -> bool:
    if valuation.requested_by_id == user.id or user.has_role("admin"):
        return True
    if valuation.property_id is None:
        return False
    prop = db.get(Property, valuation.property_id)
    return prop is not None and access.can_view_full(db, user, prop)


def serialize(db: Session, valuation: Valuation, viewer: User | None) -> dict:
    comparison: dict[str, Any] = {}
    if valuation.property_id is not None:
        previous = db.scalar(
            select(Valuation)
            .where(Valuation.property_id == valuation.property_id, Valuation.created_at < valuation.created_at)
            .order_by(Valuation.created_at.desc())
            .limit(1)
        )
        if previous is not None:
            comparison["previous_value"] = previous.predicted_value
            comparison["previous_valued_at"] = previous.created_at
            comparison["change_from_previous_pct"] = ((valuation.predicted_value - previous.predicted_value) / previous.predicted_value * 100).quantize(Decimal("0.01"))
        prop = db.get(Property, valuation.property_id)
        # Sale history is private, so it only appears for viewers entitled to the full record.
        if prop is not None and access.can_view_full(db, viewer, prop):
            comparison["last_sale_price"] = prop.last_sale_price
            comparison["last_sale_date"] = None if prop.last_sale_date is None else prop.last_sale_date.isoformat()
    interval = None
    if valuation.interval_lower is not None:
        interval = {"lower": valuation.interval_lower, "upper": valuation.interval_upper, "nominal_coverage": valuation.interval_coverage}
    return {
        "id": valuation.id,
        "property_id": valuation.property_id,
        "predicted_value": valuation.predicted_value,
        "currency": valuation.currency,
        "interval": interval,
        "predicted_at": valuation.created_at,
        "model_version": valuation.model_version.version,
        "input_summary": valuation.input_summary,
        "factors": valuation.factors,
        "historical_comparison": comparison,
        "trained_on_synthetic_data": valuation.model_version.trained_on_synthetic_data,
        "limitations": valuation.limitations,
        "disclaimer": DISCLAIMER,
    }


def prediction_monitoring(db: Session) -> dict[str, Any]:
    """Compares recent predictions with the training price distribution. Sale outcomes are not collected, so this is drift, not accuracy."""
    record = db.scalar(select(ValuationModelVersion).where(ValuationModelVersion.status == "active"))
    if record is None:
        return {"model_available": False, "predictions_scored": 0, "drift": None}
    values = [float(item) for item in db.scalars(select(Valuation.predicted_value).where(Valuation.model_version_id == record.id).order_by(Valuation.created_at.desc()).limit(1000))]
    result: dict[str, Any] = {"model_available": True, "version": record.version, "predictions_scored": len(values), "drift": None}
    if len(values) < PSI_MIN_ROWS:
        result["drift_note"] = f"At least {PSI_MIN_ROWS} predictions are needed for a drift score."
        return result
    manifest = read_manifest(get_settings().model_artifact_dir / record.artifact_path)
    psi = population_stability_index(np.array(manifest["training_log_price_sample"]), np.log(np.array(values)))
    result["drift"] = {"metric": "psi_on_log_predicted_value", "value": round(psi, 4), "status": "stable" if psi < 0.1 else "watch" if psi < 0.25 else "shifted"}
    return result

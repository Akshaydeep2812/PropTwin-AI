from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from app.models import Valuation, ValuationModelVersion

FEATURES = {"property_type": "apartment", "built_up_area_sqft": "1200", "locality": "Riverside", "city": "Sample City", "condition": "good", "construction_year": 2015, "bedrooms": 2, "bathrooms": 2}


def test_without_active_model_returns_unavailable_and_saves_nothing(make_actor, artifact_dir, db):
    response = make_actor().post("/api/v1/valuations/predict", json={"features": FEATURES})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"
    assert db.scalar(select(func.count()).select_from(Valuation)) == 0


def test_a_trained_but_unpromoted_model_is_not_used(make_actor, artifact_dir, db):
    from app.services import valuation_service

    valuation_service.sync_artifacts(db)
    assert make_actor().post("/api/v1/valuations/predict", json={"features": FEATURES}).status_code == 503


def test_prediction_returns_every_required_field(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner, locality="Riverside", city="Sample City")
    response = owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["kind"] == "ai_estimate"
    assert body["property_id"] == prop["id"]
    assert Decimal(body["predicted_value"]) > 0
    assert Decimal(body["interval"]["lower"]) < Decimal(body["predicted_value"]) < Decimal(body["interval"]["upper"])
    assert body["currency"] == "INR" and body["model_version"] == "test-model" and body["predicted_at"]
    assert body["input_summary"]["built_up_area_sqft"] == "1200.00"
    assert body["factors"] and body["trained_on_synthetic_data"] is True
    assert "not a guaranteed sale price" in body["disclaimer"]
    assert any("synthetic" in note for note in body["limitations"])
    assert body["historical_comparison"]["last_sale_price"] == "6000000.00"
    assert isinstance(body["predicted_value"], str)


def test_value_comes_from_the_model_and_changes_with_inputs(make_actor, active_model):
    actor = make_actor()
    small = actor.post("/api/v1/valuations/predict", json={"features": {**FEATURES, "built_up_area_sqft": "800"}}).json()
    large = actor.post("/api/v1/valuations/predict", json={"features": {**FEATURES, "built_up_area_sqft": "3000"}}).json()
    assert Decimal(large["predicted_value"]) > Decimal(small["predicted_value"])


def test_second_valuation_compares_to_the_first(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner)
    first = owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]}).json()
    second = owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]}).json()
    assert second["historical_comparison"]["previous_value"] == first["predicted_value"]
    assert second["historical_comparison"]["change_from_previous_pct"] == "0.00"


def test_unknown_locality_and_missing_inputs_are_disclosed(make_actor, active_model):
    body = make_actor().post("/api/v1/valuations/predict", json={"features": {"property_type": "house", "built_up_area_sqft": "1500", "locality": "Nowhere"}}).json()
    text = " ".join(body["limitations"])
    assert "no training data for this locality" in text
    assert "condition" in text and "construction_year" in text
    assert "market index" in text


def test_inputs_never_provided_are_not_reported_as_factors(make_actor, active_model):
    """Found in the browser: a blank floor was shown as the biggest thing moving an estimate."""
    body = make_actor().post("/api/v1/valuations/predict", json={"features": FEATURES}).json()
    names = {factor["factor"] for factor in body["factors"]}
    assert "Floor" not in names and "Land area" not in names and "Parking" not in names
    assert "Built-up area" in names and "Location" in names
    assert any("floor_number" in note and "total_floors" in note for note in body["limitations"])

    with_floor = make_actor().post("/api/v1/valuations/predict", json={"features": {**FEATURES, "floor_number": 3, "total_floors": 10}}).json()
    assert "Floor" in {factor["factor"] for factor in with_floor["factors"]}
    assert not any("floor_number" in note for note in with_floor["limitations"])


def test_area_outside_training_range_is_disclosed(make_actor, active_model):
    body = make_actor().post("/api/v1/valuations/predict", json={"features": {**FEATURES, "built_up_area_sqft": "12000"}}).json()
    assert any("outside the range" in note for note in body["limitations"])


def test_absurd_inputs_are_refused_not_crashed_or_stored(make_actor, active_model, db):
    response = make_actor().post("/api/v1/valuations/predict", json={"features": {**FEATURES, "built_up_area_sqft": "9000000"}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "estimate_out_of_range"
    assert db.scalar(select(func.count()).select_from(Valuation)) == 0


def test_invalid_inputs_rejected(make_actor, make_property, active_model):
    actor = make_actor()
    predict = "/api/v1/valuations/predict"
    assert actor.post(predict, json={}).status_code == 422
    assert actor.post(predict, json={"property_id": str(uuid4()), "features": FEATURES}).status_code == 422
    assert actor.post(predict, json={"features": {**FEATURES, "built_up_area_sqft": "-1"}}).status_code == 422
    assert actor.post(predict, json={"features": {**FEATURES, "property_type": "castle"}}).status_code == 422
    assert actor.post(predict, json={"features": {**FEATURES, "extra": 1}}).status_code == 422
    assert actor.post(predict, json={"property_id": str(uuid4())}).status_code == 404
    no_area = make_property(actor, built_up_area_sqft=None)
    response = actor.post(predict, json={"property_id": no_area["id"]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "insufficient_features"


def test_authorization(make_actor, make_property, active_model, client):
    owner, stranger, investor = make_actor(), make_actor(), make_actor("investor")
    draft = make_property(owner)
    listed = make_property(owner, listing_status="listed")
    predict = "/api/v1/valuations/predict"

    client.cookies.clear()
    assert client.post(predict, json={"features": FEATURES}).status_code == 401
    assert stranger.post(predict, json={"property_id": draft["id"]}).status_code == 404

    investor_view = investor.post(predict, json={"property_id": listed["id"]})
    assert investor_view.status_code == 201
    assert investor_view.json()["historical_comparison"]["last_sale_price"] is None

    private = owner.post(predict, json={"property_id": draft["id"]}).json()
    assert stranger.get(f"/api/v1/valuations/{private['id']}").status_code == 404
    assert owner.get(f"/api/v1/valuations/{private['id']}").status_code == 200

    inline = investor.post(predict, json={"features": FEATURES}).json()
    assert owner.get(f"/api/v1/valuations/{inline['id']}").status_code == 404
    assert investor.get(f"/api/v1/valuations/{inline['id']}").status_code == 200


def test_history_visibility(make_actor, make_property, active_model, client):
    owner = make_actor()
    draft, listed = make_property(owner), make_property(owner, listing_status="listed")
    owner.post("/api/v1/valuations/predict", json={"property_id": listed["id"]})
    owner.post("/api/v1/valuations/predict", json={"property_id": draft["id"]})
    client.cookies.clear()
    public = client.get(f"/api/v1/properties/{listed['id']}/valuations")
    assert public.status_code == 200 and len(public.json()) == 1
    assert "input_summary" not in public.json()[0]
    assert client.get(f"/api/v1/properties/{draft['id']}/valuations").status_code == 404


def test_batch_is_atomic(make_actor, make_property, active_model, db):
    owner, stranger = make_actor(), make_actor()
    theirs = make_property(owner)
    url = "/api/v1/valuations/batch"
    good = stranger.post(url, json={"items": [{"features": FEATURES}, {"features": {**FEATURES, "bedrooms": 3}}]})
    assert good.status_code == 201 and len(good.json()) == 2
    before = db.scalar(select(func.count()).select_from(Valuation))
    assert stranger.post(url, json={"items": [{"features": FEATURES}, {"property_id": theirs["id"]}]}).status_code == 404
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Valuation)) == before
    assert stranger.post(url, json={"items": []}).status_code == 422
    assert stranger.post(url, json={"items": [{"features": FEATURES}] * 51}).status_code == 422


def test_model_admin_routes(make_actor, artifact_dir, client):
    owner, admin = make_actor(), make_actor("admin")
    assert owner.get("/api/v1/admin/models").status_code == 403
    models = admin.get("/api/v1/admin/models").json()
    assert models[0]["version"] == "test-model" and models[0]["status"] == "candidate"
    metrics = admin.get("/api/v1/admin/models/test-model/metrics").json()["metrics"]
    assert metrics["held_out_test"]["pytorch_mlp"]["mae"] > 0
    assert admin.get("/api/v1/admin/models/nope/metrics").status_code == 404
    assert owner.post("/api/v1/admin/models/test-model/promote", json={"target": "active"}).status_code == 403


def test_promotion_requires_approval_and_passing_the_baseline_gate(make_actor, artifact_dir, db):
    admin = make_actor("admin")
    admin.get("/api/v1/admin/models")
    url = "/api/v1/admin/models/test-model/promote"
    assert admin.post(url, json={"target": "active"}).status_code == 409

    record = db.scalar(select(ValuationModelVersion))
    record.beats_baseline = False
    db.commit()
    gated = admin.post(url, json={"target": "approved"})
    assert gated.status_code == 422 and gated.json()["error"]["code"] == "failed_baseline_gate"

    record.beats_baseline = True
    db.commit()
    assert admin.post(url, json={"target": "approved"}).status_code == 200
    assert admin.post(url, json={"target": "active"}).json()["status"] == "active"
    assert admin.post("/api/v1/valuations/predict", json={"features": FEATURES}).status_code == 201


def test_activation_refuses_a_tampered_artifact(make_actor, artifact_dir, db, tmp_path, monkeypatch):
    import shutil

    from app.core.config import get_settings

    copy = tmp_path / "artifacts"
    shutil.copytree(artifact_dir, copy)
    monkeypatch.setattr(get_settings(), "model_artifact_dir", copy)
    admin = make_actor("admin")
    admin.get("/api/v1/admin/models")
    record = db.scalar(select(ValuationModelVersion))
    record.status, record.beats_baseline = "approved", True
    db.commit()
    with open(copy / "test-model" / "model.pt", "ab") as handle:
        handle.write(b"tamper")
    response = admin.post("/api/v1/admin/models/test-model/promote", json={"target": "active"})
    assert response.status_code == 503
    db.expire_all()
    assert db.scalar(select(ValuationModelVersion)).status == "approved"

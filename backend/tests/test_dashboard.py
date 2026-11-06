from decimal import Decimal

from sqlalchemy import select

from app.models import BackgroundJob
from app.models.types import utcnow


def test_dashboard_requires_login(client):
    client.cookies.clear()
    assert client.get("/api/v1/dashboard").status_code == 401


def test_empty_dashboard_reports_no_model_honestly(make_actor, artifact_dir):
    body = make_actor().get("/api/v1/dashboard").json()
    assert body["properties_accessible"] == 0 and body["latest_valuations"] == []
    assert body["model"] == {"available": False, "version": None, "trained_on_synthetic_data": None, "trained_at": None}
    assert body["data_freshness"]["latest_market_period"] is None


def test_owner_sees_only_their_own_data(make_actor, make_property, active_model):
    owner, other = make_actor(), make_actor()
    prop = make_property(owner)
    make_property(other)
    twin = owner.post(f"/api/v1/properties/{prop['id']}/twin").json()
    owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"name": "Up", "market_change_pct": "5"})

    body = owner.get("/api/v1/dashboard").json()
    assert body["properties_accessible"] == 1 and body["active_twins"] == 1
    assert body["latest_valuations"][0]["property_title"] == "Test apartment"
    assert isinstance(body["latest_valuations"][0]["predicted_value"], str)
    assert body["recent_simulations"][0]["name"] == "Up"
    assert body["model"]["available"] is True and body["model"]["trained_on_synthetic_data"] is True

    theirs = other.get("/api/v1/dashboard").json()
    assert theirs["active_twins"] == 0 and theirs["latest_valuations"] == [] and theirs["recent_simulations"] == []


def test_investor_counts_public_listings_and_favorites(make_actor, make_property):
    owner, investor = make_actor(), make_actor("investor")
    listed = make_property(owner, listing_status="listed")
    make_property(owner)
    investor.put(f"/api/v1/saved-properties/{listed['id']}")
    body = investor.get("/api/v1/dashboard").json()
    assert body["properties_accessible"] == 1 and body["saved_properties"] == 1


def test_trend_is_oldest_first(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner)
    for _ in range(3):
        owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]})
    trend = owner.get("/api/v1/dashboard").json()["valuation_trend"]
    assert [item["predicted_at"] for item in trend] == sorted(item["predicted_at"] for item in trend)


def test_monitoring_is_admin_only_and_reports_real_counts(make_actor, make_property, active_model, db):
    owner, admin = make_actor(), make_actor("admin")
    make_property(owner)
    owner.post("/api/v1/valuations/predict", json={"features": {"property_type": "house", "built_up_area_sqft": "1500"}})
    db.add(BackgroundJob(kind="x", payload={}, status="dead", attempts=5, run_after=utcnow(), last_error="boom"))
    db.commit()

    assert owner.get("/api/v1/admin/monitoring").status_code == 403
    assert owner.get("/api/v1/admin/transactions").status_code == 403
    body = admin.get("/api/v1/admin/monitoring").json()
    assert body["users"] == 2 and body["properties"] == 1
    assert body["prediction"]["predictions_scored"] == 1 and body["prediction"]["drift"] is None
    assert "At least" in body["prediction"]["drift_note"]
    assert body["dead_jobs"][0]["last_error"] == "boom"
    assert admin.get("/api/v1/admin/transactions").json()["total"] == 0


def test_drift_score_appears_with_enough_predictions(make_actor, active_model):
    admin = make_actor("admin")
    for area in range(800, 2300, 50):
        admin.post("/api/v1/valuations/predict", json={"features": {"property_type": "apartment", "built_up_area_sqft": str(area), "locality": "Riverside"}})
    drift = admin.get("/api/v1/admin/monitoring").json()["prediction"]["drift"]
    assert drift["metric"] == "psi_on_log_predicted_value" and drift["status"] in ("stable", "watch", "shifted")
    assert Decimal(str(drift["value"])) >= 0


def test_readiness_reports_dependencies(client, artifact_dir):
    body = client.get("/api/v1/health/ready").json()
    assert body["status"] == "ready" and body["database"] == "ok" and body["model_available"] is False

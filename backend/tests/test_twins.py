from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import AuditLog, BackgroundJob, DigitalTwinSnapshot, SimulationRun, Valuation
from app.models.types import utcnow
from app.services import jobs, simulation
from app.workers import runner


def _twin(owner, prop) -> dict:
    response = owner.post(f"/api/v1/properties/{prop['id']}/twin")
    assert response.status_code == 201, response.text
    return response.json()


def test_formula_matches_the_specification_exactly():
    result = simulation.calculate(simulation.ScenarioInputs(baseline_value=Decimal("8000000.00"), market_change_pct=Decimal("5")))
    assert result.scenario_value == Decimal("8400000.00")
    assert result.absolute_difference == Decimal("400000.00")
    assert result.percentage_difference == Decimal("5.0000")


def test_decline_and_yield_and_maintenance():
    result = simulation.calculate(
        simulation.ScenarioInputs(
            baseline_value=Decimal("5000000.00"),
            market_change_pct=Decimal("-10"),
            monthly_rent=Decimal("20000.00"),
            monthly_rent_change_pct=Decimal("5"),
            annual_maintenance_cost=Decimal("60000.00"),
            maintenance_change_pct=Decimal("20"),
        )
    )
    assert result.scenario_value == Decimal("4500000.00")
    assert result.absolute_difference == Decimal("-500000.00")
    assert result.percentage_difference == Decimal("-10.0000")
    assert result.annual_rental_income == Decimal("252000.00")
    assert result.rental_yield_pct == Decimal("5.6000")
    assert result.annual_maintenance_cost == Decimal("72000.00")


def test_calculation_is_decimal_exact_not_float():
    result = simulation.calculate(simulation.ScenarioInputs(baseline_value=Decimal("0.30"), market_change_pct=Decimal("10")))
    assert result.scenario_value == Decimal("0.33")


def test_missing_rent_gives_no_yield_rather_than_zero():
    result = simulation.calculate(simulation.ScenarioInputs(baseline_value=Decimal("100.00")))
    assert result.annual_rental_income is None and result.rental_yield_pct is None and result.annual_maintenance_cost is None


def test_create_twin_stores_state_values_and_first_snapshot(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    assert twin["version"] == 1
    assert Decimal(twin["current_estimated_value"]) > 0
    assert twin["state"]["condition"] == "good"
    assert twin["valuation_is_stale"] is False
    assert "no live sensor feed" in twin["twin_type"]
    assert "address_line1" not in twin["state"]
    history = owner.get(f"/api/v1/twins/{twin['id']}/history").json()
    assert history["total"] == 1 and history["items"][0]["reason"] == "created"


def test_twin_without_a_model_reports_no_estimate(make_actor, make_property, artifact_dir):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    assert twin["current_estimated_value"] is None and twin["valuation_is_stale"] is True
    response = owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"market_change_pct": "5"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "baseline_required"


def test_only_one_twin_per_property(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner)
    _twin(owner, prop)
    assert owner.post(f"/api/v1/properties/{prop['id']}/twin").status_code == 409


def test_property_update_syncs_twin_and_preserves_old_snapshots(make_actor, make_property, active_model, db):
    owner = make_actor()
    prop = make_property(owner)
    twin = _twin(owner, prop)
    original = db.scalar(select(DigitalTwinSnapshot).where(DigitalTwinSnapshot.version == 1))
    original_state = dict(original.state)

    owner.patch(f"/api/v1/properties/{prop['id']}", json={"condition": "excellent"})
    updated = owner.get(f"/api/v1/properties/{prop['id']}/twin").json()
    assert updated["version"] == 2 and updated["state"]["condition"] == "excellent"
    assert updated["valuation_is_stale"] is True

    snapshots = owner.get(f"/api/v1/twins/{twin['id']}/history").json()["items"]
    assert [item["version"] for item in snapshots] == [2, 1]
    assert snapshots[0]["changed_fields"] == ["condition"] and snapshots[0]["reason"] == "property_sync"
    assert snapshots[1]["state"]["condition"] == "good"
    db.rollback()
    assert db.get(DigitalTwinSnapshot, original.id).state == original_state
    assert db.scalar(select(AuditLog).where(AuditLog.action == "twin.synced")) is not None


def test_untracked_edit_does_not_create_a_snapshot(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner)
    _twin(owner, prop)
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"title": "A new title"})
    assert owner.get(f"/api/v1/properties/{prop['id']}/twin").json()["version"] == 1


def test_background_job_revalues_after_sync(make_actor, make_property, active_model, db):
    owner = make_actor()
    prop = make_property(owner)
    twin = _twin(owner, prop)
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"built_up_area_sqft": "2400.00"})
    assert owner.get(f"/api/v1/properties/{prop['id']}/twin").json()["valuation_is_stale"] is True

    db.expire_all()
    assert runner.run_pass(db) == 1
    refreshed = owner.get(f"/api/v1/properties/{prop['id']}/twin").json()
    assert refreshed["valuation_is_stale"] is False
    assert Decimal(refreshed["current_estimated_value"]) > Decimal(twin["current_estimated_value"])
    assert db.scalar(select(BackgroundJob)).status == "succeeded"
    assert refreshed["version"] == 3


def test_failed_job_retries_with_backoff_then_goes_dead(db):
    job = jobs.enqueue(db, "always_fails", {})
    db.commit()

    def boom(_db, _payload):
        raise RuntimeError("provider down")

    handlers = {"always_fails": boom}
    assert jobs.run_one(db, handlers) is True
    db.expire_all()
    job = db.scalar(select(BackgroundJob))
    assert job.status == "queued" and job.attempts == 1 and "provider down" in job.last_error
    assert job.run_after > utcnow()
    assert jobs.run_one(db, handlers) is False

    for _ in range(4):
        job = db.scalar(select(BackgroundJob))
        job.run_after = utcnow()
        db.commit()
        jobs.run_one(db, handlers)
        db.expire_all()
    assert db.scalar(select(BackgroundJob)).status == "dead"


def test_failed_job_rolls_back_its_partial_work(make_actor, make_property, active_model, db):
    owner = make_actor()
    prop = make_property(owner)

    def partial(session, _payload):
        session.add(AuditLog(action="partial.write", entity_type="test", details={}))
        session.flush()
        raise RuntimeError("after writing")

    jobs.enqueue(db, "partial", {})
    db.commit()
    jobs.run_one(db, {"partial": partial})
    db.expire_all()
    assert db.scalar(select(AuditLog).where(AuditLog.action == "partial.write")) is None


def test_market_formula_scenario_is_labeled_and_never_changes_state(make_actor, make_property, active_model, db):
    owner = make_actor()
    prop = make_property(owner)
    twin = _twin(owner, prop)
    predictions_before = len(db.scalars(select(Valuation)).all())
    response = owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"name": "Up 5%", "market_change_pct": "5", "monthly_rent_change_pct": "10"})
    assert response.status_code == 201, response.text
    run = response.json()
    baseline = Decimal(twin["current_estimated_value"])
    assert run["kind"] == "hypothetical_simulation" and run["method"] == "formula"
    assert "not a new model prediction" in run["calculation_note"]
    assert Decimal(run["baseline_value"]) == baseline
    assert Decimal(run["scenario_value"]) == (baseline * Decimal("1.05")).quantize(Decimal("0.01"))
    assert Decimal(run["annual_rental_income"]) == Decimal("330000.00")
    assert Decimal({item["name"]: item["value"] for item in run["assumptions"]}["market_change_pct"]) == Decimal("5")
    assert any("not a forecast" in note for note in run["limitations"])

    after = owner.get(f"/api/v1/properties/{prop['id']}/twin").json()
    assert after["version"] == twin["version"] and after["current_estimated_value"] == twin["current_estimated_value"]
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["condition"] == "good"
    db.expire_all()
    assert len(db.scalars(select(Valuation)).all()) == predictions_before


def test_same_scenario_twice_gives_the_same_result(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    url = f"/api/v1/twins/{twin['id']}/simulate"
    for payload in ({"market_change_pct": "-10"}, {"condition_after": "excellent", "market_change_pct": "3"}):
        first, second = owner.post(url, json=payload).json(), owner.post(url, json=payload).json()
        assert first["scenario_value"] == second["scenario_value"] and first["method"] == second["method"]


def test_renovation_condition_really_reruns_the_model(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner, condition="fair"))
    run = owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"condition_after": "excellent"}).json()
    assert run["method"] == "model_rerun"
    assert "model rerun" in run["calculation_note"]
    assert run["scenario_value"] != run["baseline_value"]


def test_rerun_needs_a_model_and_does_not_fall_back_silently(make_actor, make_property, active_model, db):
    owner = make_actor()
    twin = _twin(owner, make_property(owner, condition="fair"))
    active_model.status = "retired"
    db.merge(active_model)
    db.commit()
    url = f"/api/v1/twins/{twin['id']}/simulate"
    assert owner.post(url, json={"condition_after": "excellent"}).status_code == 503
    assert owner.post(url, json={"market_change_pct": "5"}).status_code == 201


def test_double_counting_renovation_is_rejected(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    response = owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"condition_after": "excellent", "renovation_value_uplift_pct": "10"})
    assert response.status_code == 422


@pytest.mark.parametrize("bad", [{"market_change_pct": "-95"}, {"market_change_pct": "abc"}, {"renovation_value_uplift_pct": "-1"}, {"unknown": 1}])
def test_invalid_scenarios_rejected(make_actor, make_property, active_model, bad):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    assert owner.post(f"/api/v1/twins/{twin['id']}/simulate", json=bad).status_code == 422


def test_missing_rent_is_disclosed(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner, monthly_rent=None))
    run = owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"market_change_pct": "1"}).json()
    assert run["annual_rental_income"] is None and run["rental_yield_pct"] is None
    assert any("No rent" in note for note in run["limitations"])


def test_operating_update_writes_snapshot_and_feeds_simulation(make_actor, make_property, active_model):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    url = f"/api/v1/twins/{twin['id']}"
    updated = owner.patch(url, json={"annual_maintenance_cost": "50000.00", "maintenance_notes": "Roof check"}).json()
    assert updated["version"] == 2 and updated["state"]["operating"]["maintenance_notes"] == "Roof check"
    assert owner.patch(url, json={}).json()["version"] == 2
    run = owner.post(f"{url}/simulate", json={"maintenance_change_pct": "20"}).json()
    assert run["annual_maintenance_cost"] == "60000.00"


def test_permissions(make_actor, make_property, active_model, client):
    owner, investor, stranger, verifier = make_actor(), make_actor("investor"), make_actor(), make_actor("verifier")
    draft, listed = make_property(owner), make_property(owner, listing_status="listed")
    draft_twin, listed_twin = _twin(owner, draft), _twin(owner, listed)
    scenario = {"market_change_pct": "5"}

    assert stranger.post(f"/api/v1/properties/{draft['id']}/twin").status_code == 404
    assert stranger.post(f"/api/v1/properties/{listed['id']}/twin").status_code == 403
    client.cookies.clear()
    assert client.get(f"/api/v1/properties/{listed['id']}/twin").status_code == 401

    for reader in (investor, stranger):
        assert reader.get(f"/api/v1/properties/{draft['id']}/twin").status_code == 404
        assert reader.post(f"/api/v1/twins/{draft_twin['id']}/simulate", json=scenario).status_code == 404

    assert investor.get(f"/api/v1/properties/{listed['id']}/twin").status_code == 200
    assert stranger.get(f"/api/v1/properties/{listed['id']}/twin").status_code == 404
    assert investor.patch(f"/api/v1/twins/{listed_twin['id']}", json={"maintenance_notes": "x"}).status_code == 403
    assert investor.get(f"/api/v1/twins/{listed_twin['id']}/history").status_code == 403
    assert verifier.post(f"/api/v1/twins/{listed_twin['id']}/simulate", json=scenario).status_code == 404

    assert investor.post(f"/api/v1/twins/{listed_twin['id']}/simulate", json=scenario).status_code == 201
    owner_run = owner.post(f"/api/v1/twins/{listed_twin['id']}/simulate", json=scenario)
    assert owner_run.status_code == 201
    assert investor.get(f"/api/v1/twins/{listed_twin['id']}/simulations").json()["total"] == 1
    assert owner.get(f"/api/v1/twins/{listed_twin['id']}/simulations").json()["total"] == 2


def test_investor_valuation_does_not_move_the_owners_twin(make_actor, make_property, active_model):
    owner, investor = make_actor(), make_actor("investor")
    listed = make_property(owner, listing_status="listed")
    twin = _twin(owner, listed)
    investor.post("/api/v1/valuations/predict", json={"property_id": listed["id"]})
    assert owner.get(f"/api/v1/properties/{listed['id']}/twin").json()["version"] == twin["version"]
    owner.post("/api/v1/valuations/predict", json={"property_id": listed["id"]})
    assert owner.get(f"/api/v1/properties/{listed['id']}/twin").json()["version"] == twin["version"] + 1


def test_simulations_are_persisted_with_assumptions(make_actor, make_property, active_model, db):
    owner = make_actor()
    twin = _twin(owner, make_property(owner))
    owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"market_change_pct": "-10", "renovation_cost": "100000"})
    run = db.scalar(select(SimulationRun))
    assert {item.name: item.unit for item in run.assumptions} == {
        "market_change_pct": "percent", "renovation_value_uplift_pct": "percent", "renovation_cost": "currency", "monthly_rent_change_pct": "percent", "maintenance_change_pct": "percent",
    }


def test_retention_purges_only_what_has_expired(make_actor, db):
    from datetime import timedelta

    from app.models import Notification
    from app.services import retention

    user_id = make_actor().user["id"]
    import uuid

    uid = uuid.UUID(user_id)
    now = utcnow()
    db.add_all(
        [
            AuditLog(action="old", entity_type="t", details={}, created_at=now - timedelta(days=800)),
            AuditLog(action="recent", entity_type="t", details={}, created_at=now - timedelta(days=100)),
            Notification(user_id=uid, kind="k", title="old read", read_at=now - timedelta(days=400)),
            Notification(user_id=uid, kind="k", title="old unread", created_at=now - timedelta(days=400)),
            BackgroundJob(kind="k", payload={}, status="succeeded", run_after=now, updated_at=now - timedelta(days=40)),
            BackgroundJob(kind="k", payload={}, status="dead", run_after=now, updated_at=now - timedelta(days=40)),
        ]
    )
    db.commit()
    counts = retention.purge(db)
    assert counts["audit_logs"] == 1 and counts["notifications"] == 1 and counts["background_jobs"] == 1
    db.expire_all()
    actions = {row.action for row in db.scalars(select(AuditLog))}
    assert "old" not in actions and "recent" in actions
    assert [row.title for row in db.scalars(select(Notification))] == ["old unread"]
    assert [row.status for row in db.scalars(select(BackgroundJob))] == ["dead"]

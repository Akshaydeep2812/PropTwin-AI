from datetime import date
from decimal import Decimal

from app.core.config import Settings, get_settings
from app.models import MarketObservation
from app.services import auth_service


def _add_market(session_factory, locality="Riverside", city="Sample City", synthetic=True):
    today = date.today().replace(day=1)
    with session_factory() as session:
        for years, index in ((6, "100"), (5, "110"), (1, "150"), (0, "165")):
            session.add(
                MarketObservation(
                    locality=locality,
                    city=city,
                    period=today.replace(year=today.year - years),
                    price_index=Decimal(index),
                    median_price_per_sqft=Decimal("6000"),
                    median_monthly_rent_per_sqft=Decimal("20"),
                    source="test",
                    is_synthetic=synthetic,
                )
            )
        session.commit()


def test_market_overview_derives_growth_and_yield(client, session_factory):
    _add_market(session_factory)
    body = client.get("/api/v1/market/localities").json()
    row = body["localities"][0]
    assert body["cities"] == ["Sample City"] and body["any_synthetic"] is True
    assert Decimal(row["change_12m_pct"]) == Decimal("10.00")
    # 20 a month, 12 months, against 6000: exactly 4%.
    assert Decimal(row["gross_yield_pct"]) == Decimal("4.00")
    assert Decimal(row["cagr_5y_pct"]) == Decimal("8.45")
    assert row["is_synthetic"] is True


def test_market_overview_is_empty_without_data(client):
    assert client.get("/api/v1/market/localities").json() == {"localities": [], "cities": [], "latest_period": None, "any_synthetic": False}


def test_market_trend_and_unknown_locality(client, session_factory):
    _add_market(session_factory)
    points = client.get("/api/v1/market/localities/Riverside/trend").json()
    assert [Decimal(point["price_index"]) for point in points] == [Decimal("100"), Decimal("110"), Decimal("150"), Decimal("165")]
    assert client.get("/api/v1/market/localities/Nowhere/trend").status_code == 404


def test_market_excludes_future_periods(client, session_factory):
    _add_market(session_factory)
    today = date.today().replace(day=1)
    with session_factory() as session:
        session.add(MarketObservation(locality="Riverside", city="Sample City", period=today.replace(year=today.year + 1), price_index=Decimal("999"), source="test", is_synthetic=True))
        session.commit()
    assert Decimal(client.get("/api/v1/market/localities").json()["localities"][0]["price_index"]) == Decimal("165")


def test_insights_without_estimate_say_so_and_invent_nothing(client, make_actor, make_property, artifact_dir):
    owner = make_actor()
    prop = make_property(owner)
    body = owner.get(f"/api/v1/properties/{prop['id']}/insights").json()
    assert body["estimate"] is None and body["price_position"] is None and body["asking_vs_estimate_pct"] is None
    assert any("No AI estimate" in note["text"] for note in body["takeaways"])
    assert any("No verifier" in note["text"] for note in body["takeaways"])


def test_insights_compare_asking_price_with_market_and_estimate(make_actor, make_property, active_model, session_factory):
    _add_market(session_factory)
    owner = make_actor()
    prop = make_property(owner, locality="Riverside", city="Sample City", built_up_area_sqft="1000.00", asking_price="9000000.00", monthly_rent="30000.00", listing_status="listed")
    assert owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]}).status_code == 201

    body = owner.get(f"/api/v1/properties/{prop['id']}/insights").json()
    assert Decimal(body["asking_per_sqft"]) == Decimal("9000.00")
    assert Decimal(body["premium_to_market_pct"]) == Decimal("50.00")
    # 30000 x 12 / 9000000 = 4%.
    assert Decimal(body["gross_yield_pct"]) == Decimal("4.00")
    assert body["estimate"]["is_current"] is True and body["status"]["has_estimate"] is True
    value, lower, upper, asking = (Decimal(x) for x in (body["estimate"]["value"], body["estimate"]["lower"], body["estimate"]["upper"], body["asking_price"]))
    expected = "below_range" if asking < lower else "above_range" if asking > upper else "within_range"
    assert body["price_position"] == expected
    assert Decimal(body["asking_vs_estimate_pct"]) == ((asking - value) / value * 100).quantize(Decimal("0.01"))
    assert any("50.00% above the locality median" in note["text"] for note in body["takeaways"])


def test_insights_flag_an_estimate_made_before_the_property_changed(make_actor, make_property, active_model):
    owner = make_actor()
    prop = make_property(owner)
    owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]})
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"bedrooms": 4})
    body = owner.get(f"/api/v1/properties/{prop['id']}/insights").json()
    assert body["status"]["estimate_current"] is False
    assert any("out of date" in note["text"] for note in body["takeaways"])


def test_changes_the_model_never_saw_leave_an_estimate_current(make_actor, make_property, active_model, session_factory):
    owner = make_actor()
    prop = make_property(owner, built_up_area_sqft="1250.00")
    owner.post("/api/v1/valuations/predict", json={"property_id": prop["id"]})
    assert owner.patch(f"/api/v1/properties/{prop['id']}", json={"description": "New words", "asking_price": "9100000.00"}).status_code == 200
    body = owner.get(f"/api/v1/properties/{prop['id']}/insights").json()
    assert body["status"]["estimate_current"] is True
    assert not any("out of date" in note["text"] for note in body["takeaways"])

    # Sending the same area in another form is not a change either.
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"built_up_area_sqft": "1250"})
    assert owner.get(f"/api/v1/properties/{prop['id']}/insights").json()["status"]["estimate_current"] is True
    owner.patch(f"/api/v1/properties/{prop['id']}", json={"built_up_area_sqft": "1400.00"})
    assert owner.get(f"/api/v1/properties/{prop['id']}/insights").json()["status"]["estimate_current"] is False


def test_verification_queue_names_each_property(make_actor, make_property):
    owner, verifier = make_actor(), make_actor("verifier")
    prop = make_property(owner, title="Named property")
    png = b"%PDF-1.4 test"
    assert owner.post(f"/api/v1/properties/{prop['id']}/documents", files={"file": ("a.pdf", png, "application/pdf")}, data={"document_type": "other"}).status_code == 201
    assert owner.post(f"/api/v1/properties/{prop['id']}/verification-requests", json={}).status_code == 201
    assert verifier.get("/api/v1/verification/queue").json()["items"][0]["property_title"] == "Named property"


def test_insights_respect_visibility_and_hide_completeness_from_others(client, make_actor, make_property, artifact_dir):
    owner, other = make_actor(), make_actor("investor")
    draft = make_property(owner, listing_status="draft")
    listed = make_property(owner, listing_status="listed")
    client.cookies.clear()
    assert client.get(f"/api/v1/properties/{draft['id']}/insights").status_code == 404
    assert other.get(f"/api/v1/properties/{draft['id']}/insights").status_code == 404
    assert other.get(f"/api/v1/properties/{listed['id']}/insights").json()["completeness"] is None
    completeness = owner.get(f"/api/v1/properties/{listed['id']}/insights").json()["completeness"]
    assert 0 <= completeness["percent"] <= 100 and "A photo" in completeness["missing"]


def test_portfolio_totals_and_next_action(make_actor, make_property, active_model):
    owner, stranger = make_actor(), make_actor()
    first = make_property(owner, monthly_rent="10000.00")
    second = make_property(owner, monthly_rent="20000.00")
    make_property(stranger)
    owner.post("/api/v1/valuations/predict", json={"property_id": first["id"]})

    body = owner.get("/api/v1/properties/mine/portfolio").json()
    rows = {row["id"]: row for row in body["items"]}
    assert body["total_properties"] == 2 and body["estimated_count"] == 1
    assert Decimal(body["total_annual_rent"]) == Decimal("360000.00")
    assert rows[first["id"]]["next_action"]["label"] == "Create a digital twin"
    assert rows[second["id"]]["next_action"]["label"] == "Get an AI estimate"
    assert Decimal(body["total_estimate"]) == Decimal(rows[first["id"]]["estimate"])


def test_portfolio_requires_login(client):
    client.cookies.clear()
    assert client.get("/api/v1/properties/mine/portfolio").status_code == 401


def test_onboarding_ticks_only_what_really_happened(make_actor, make_property, active_model):
    owner = make_actor()
    steps = lambda: {step["key"]: step for step in owner.get("/api/v1/dashboard").json()["onboarding"]["steps"]}  # noqa: E731
    before = steps()
    assert not any(step["done"] for step in before.values())
    assert before["estimate"]["href"] == "/properties/new"

    prop = make_property(owner)
    after_register = steps()
    assert after_register["register"]["done"] and not after_register["estimate"]["done"]
    assert after_register["estimate"]["href"] == f"/valuations?property={prop['id']}"

    twin = owner.post(f"/api/v1/properties/{prop['id']}/twin").json()
    owner.post(f"/api/v1/twins/{twin['id']}/simulate", json={"name": "Up", "market_change_pct": "5"})
    after_twin = steps()
    assert after_twin["twin"]["done"] and after_twin["scenario"]["done"] and after_twin["estimate"]["done"]
    assert not after_twin["chain"]["done"] and not after_twin["verify"]["done"]


def test_onboarding_is_specific_to_the_role(make_actor, make_property):
    investor = make_actor("investor")
    body = investor.get("/api/v1/dashboard").json()["onboarding"]
    assert body["role"] == "investor" and body["completed"] == 0
    listed = make_property(make_actor(), listing_status="listed")
    assert investor.put(f"/api/v1/saved-properties/{listed['id']}").status_code == 204
    steps = {step["key"]: step["done"] for step in investor.get("/api/v1/dashboard").json()["onboarding"]["steps"]}
    assert steps["save"] and not steps["shortlist"]
    assert make_actor("verifier").get("/api/v1/dashboard").json()["onboarding"]["role"] == "verifier"
    assert make_actor("admin").get("/api/v1/dashboard").json()["onboarding"]["role"] == "admin"


def _demo_user(session_factory, email="demo.owner@proptwin.example"):
    with session_factory() as session:
        user = auth_service.register_user(session, email, "correct-horse-battery", "Demo Owner", "owner")
        user.is_demo = True
        session.commit()


def test_demo_login_is_off_by_default(client, session_factory, monkeypatch):
    # The field's own default, whatever the surrounding environment has set.
    assert Settings.model_fields["demo_login_enabled"].default is False
    monkeypatch.setattr(get_settings(), "demo_login_enabled", False)
    _demo_user(session_factory)
    assert client.get("/api/v1/auth/demo-accounts").json() == []
    assert client.post("/api/v1/auth/demo-login", json={"email": "demo.owner@proptwin.example"}).status_code == 404


def test_demo_login_opens_only_flagged_accounts(client, session_factory, make_actor, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_login_enabled", True)
    _demo_user(session_factory)
    real = make_actor(email="real@example.com")
    accounts = client.get("/api/v1/auth/demo-accounts").json()
    assert [account["email"] for account in accounts] == ["demo.owner@proptwin.example"]
    assert set(accounts[0]) == {"email", "display_name", "roles"}

    client.cookies.clear()
    response = client.post("/api/v1/auth/demo-login", json={"email": "demo.owner@proptwin.example"})
    assert response.status_code == 200 and response.json()["user"]["is_demo"] is True
    assert client.post("/api/v1/auth/demo-login", json={"email": real.user["email"]}).status_code == 404


def test_production_refuses_demo_login():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="DEMO_LOGIN_ENABLED"):
        Settings(app_env="production", secret_key="x" * 40, cookie_secure=True, demo_login_enabled=True, _env_file=None)

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, PropertyOwnershipHistory

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
PDF = b"%PDF-1.7 test"


def test_create_requires_owner_role(make_actor, property_payload):
    assert make_actor("investor").post("/api/v1/properties", json=property_payload).status_code == 403


def test_create_writes_history_and_audit_and_cleans_amenities(make_actor, make_property, db):
    owner = make_actor()
    prop = make_property(owner)
    assert prop["owner_id"] == owner.user["id"]
    assert prop["amenities"] == ["gym", "lift"]
    assert prop["verification_status"] == "unverified"
    assert prop["property_age"] is not None
    assert db.scalar(select(PropertyOwnershipHistory)) is not None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "property.created")) is not None


@pytest.mark.parametrize(
    "bad",
    [
        {"built_up_area_sqft": "-5"},
        {"bedrooms": -1},
        {"property_type": "castle"},
        {"latitude": "91"},
        {"construction_year": 1500},
        {"asking_price": "0"},
        {"floor_number": 9, "total_floors": 3},
        {"owner_id": str(uuid.uuid4())},
        {"verification_status": "verified"},
    ],
)
def test_invalid_input_rejected(make_actor, property_payload, bad):
    assert make_actor().post("/api/v1/properties", json={**property_payload, **bad}).status_code == 422


def test_owner_cannot_self_verify_by_patch(make_actor, make_property):
    owner = make_actor()
    prop = make_property(owner)
    assert owner.patch(f"/api/v1/properties/{prop['id']}", json={"verification_status": "verified"}).status_code == 422


def test_draft_is_hidden_from_others(make_actor, make_property, client):
    owner, stranger = make_actor(), make_actor()
    url = f"/api/v1/properties/{make_property(owner)['id']}"
    assert stranger.get(url).status_code == 404
    client.cookies.clear()
    assert client.get(url).status_code == 404
    assert owner.get(url).status_code == 200


def test_public_view_hides_private_fields(make_actor, make_property, client):
    owner = make_actor()
    prop = make_property(owner, listing_status="listed", latitude="17.123456", longitude="78.123456")
    client.cookies.clear()
    body = client.get(f"/api/v1/properties/{prop['id']}").json()
    assert body["access_level"] == "public"
    for field in ("address_line1", "postal_code", "owner_id", "latitude", "longitude", "last_sale_price"):
        assert field not in body
    listing = client.get("/api/v1/properties").json()["items"][0]
    assert "address_line1" not in listing and "owner_id" not in listing
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["access_level"] == "full"


def test_idor_other_users_cannot_modify(make_actor, make_property):
    owner, stranger = make_actor(), make_actor()
    hidden = make_property(owner)
    listed = make_property(owner, listing_status="listed")
    assert stranger.patch(f"/api/v1/properties/{hidden['id']}", json={"title": "Hacked"}).status_code == 404
    assert stranger.delete(f"/api/v1/properties/{hidden['id']}").status_code == 404
    assert stranger.patch(f"/api/v1/properties/{listed['id']}", json={"title": "Hacked"}).status_code == 403
    assert stranger.delete(f"/api/v1/properties/{listed['id']}").status_code == 403
    assert owner.get(f"/api/v1/properties/{listed['id']}").json()["title"] == "Test apartment"


def test_admin_can_manage_any_property(make_actor, make_property):
    owner, admin = make_actor(), make_actor("admin")
    prop = make_property(owner)
    assert admin.patch(f"/api/v1/properties/{prop['id']}", json={"title": "Moderated title"}).status_code == 200


def test_archive_keeps_the_record_but_hides_it(make_actor, make_property, client):
    owner = make_actor()
    prop = make_property(owner, listing_status="listed")
    assert owner.delete(f"/api/v1/properties/{prop['id']}").status_code == 204
    client.cookies.clear()
    assert client.get(f"/api/v1/properties/{prop['id']}").status_code == 404
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["listing_status"] == "archived"
    assert owner.get("/api/v1/properties/mine").json()["total"] == 0
    assert owner.get("/api/v1/properties/mine?include_archived=true").json()["total"] == 1


def test_search_filter_sort_paginate(make_actor, make_property, client):
    owner = make_actor()
    make_property(owner, listing_status="listed", title="Cheap flat", city="Alpha", asking_price="1000000.00", built_up_area_sqft="500.00")
    make_property(owner, listing_status="listed", title="Big villa", city="Beta", property_type="villa", asking_price="9000000.00", built_up_area_sqft="4000.00")
    make_property(owner, listing_status="listed", title="Mid flat", city="Alpha", asking_price="5000000.00", built_up_area_sqft="1000.00")
    make_property(owner, title="Unlisted draft", city="Alpha")
    client.cookies.clear()

    def get(**params):
        return client.get("/api/v1/properties", params=params).json()

    assert get()["total"] == 3
    assert get(city="Alpha")["total"] == 2
    assert get(property_type="villa")["items"][0]["title"] == "Big villa"
    assert get(min_price="2000000", max_price="6000000")["items"][0]["title"] == "Mid flat"
    assert get(min_area="900", max_area="1100")["total"] == 1
    assert [p["title"] for p in get(sort="price_asc")["items"]] == ["Cheap flat", "Mid flat", "Big villa"]
    assert get(q="villa")["total"] == 1
    page = get(page=2, page_size=2, sort="price_asc")
    assert page["total"] == 3 and len(page["items"]) == 1 and page["items"][0]["title"] == "Big villa"
    assert client.get("/api/v1/properties", params={"sort": "id; DROP TABLE users"}).status_code == 422
    assert get(q="%")["total"] == 0


def test_search_is_not_injectable(make_actor, make_property, client):
    make_property(make_actor(), listing_status="listed")
    client.cookies.clear()
    assert client.get("/api/v1/properties", params={"q": "' OR '1'='1"}).json()["total"] == 0
    assert client.get("/api/v1/properties", params={"city": "x' OR 1=1 -- "}).json()["total"] == 0


def test_compare_limits_and_hides_drafts(make_actor, make_property, client):
    owner = make_actor()
    a, b = make_property(owner, listing_status="listed"), make_property(owner, listing_status="listed")
    draft = make_property(owner)
    client.cookies.clear()
    assert len(client.get("/api/v1/properties/compare", params={"ids": [a["id"], b["id"]]}).json()) == 2
    assert client.get("/api/v1/properties/compare", params={"ids": [a["id"], draft["id"]]}).status_code == 404
    assert client.get("/api/v1/properties/compare", params={"ids": [a["id"]]}).status_code == 422


def test_favorites(make_actor, make_property):
    owner, investor = make_actor(), make_actor("investor")
    listed, draft = make_property(owner, listing_status="listed"), make_property(owner)
    assert investor.put(f"/api/v1/saved-properties/{listed['id']}").status_code == 204
    assert investor.put(f"/api/v1/saved-properties/{listed['id']}").status_code == 204
    assert investor.put(f"/api/v1/saved-properties/{draft['id']}").status_code == 404
    assert [p["id"] for p in investor.get("/api/v1/saved-properties").json()] == [listed["id"]]
    assert investor.delete(f"/api/v1/saved-properties/{listed['id']}").status_code == 204
    assert investor.get("/api/v1/saved-properties").json() == []


def test_image_upload_validates_bytes_not_names(make_actor, make_property, client):
    owner = make_actor()
    url = f"/api/v1/properties/{make_property(owner, listing_status='listed')['id']}/images"
    assert owner.post(url, files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")}).status_code == 415
    assert owner.post(url, files={"file": ("empty.png", b"", "image/png")}).status_code == 422
    created = owner.post(url, files={"file": ("../../evil.exe", PNG, "application/x-msdownload")})
    assert created.status_code == 201 and created.json()["content_type"] == "image/png"
    client.cookies.clear()
    fetched = client.get(f"{url}/{created.json()['id']}")
    assert fetched.status_code == 200 and fetched.content == PNG
    assert fetched.headers["x-content-type-options"] == "nosniff"


def test_documents_are_private(make_actor, make_property, client):
    owner, stranger, investor = make_actor(), make_actor(), make_actor("investor")
    url = f"/api/v1/properties/{make_property(owner, listing_status='listed')['id']}/documents"
    doc = owner.post(url, files={"file": ("deed.pdf", PDF, "application/pdf")}, data={"document_type": "sale_deed"}).json()
    assert stranger.post(url, files={"file": ("x.pdf", PDF, "application/pdf")}, data={"document_type": "sale_deed"}).status_code == 403
    for reader in (stranger, investor):
        assert reader.get(url).status_code == 403
        assert reader.get(f"{url}/{doc['id']}").status_code == 403
    client.cookies.clear()
    assert client.get(url).status_code == 401
    download = owner.get(f"{url}/{doc['id']}")
    assert download.content == PDF and "attachment" in download.headers["content-disposition"]


def _submit(owner, prop):
    owner.post(f"/api/v1/properties/{prop['id']}/documents", files={"file": ("d.pdf", PDF, "application/pdf")}, data={"document_type": "sale_deed"})
    return owner.post(f"/api/v1/properties/{prop['id']}/verification-requests", json={"notes": "please"})


def test_verification_requires_documents_and_single_open_request(make_actor, make_property):
    owner = make_actor()
    prop = make_property(owner)
    assert owner.post(f"/api/v1/properties/{prop['id']}/verification-requests", json={}).status_code == 422
    assert _submit(owner, prop).status_code == 201
    assert owner.post(f"/api/v1/properties/{prop['id']}/verification-requests", json={}).status_code == 409
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["verification_status"] == "pending"


def test_verifier_workflow_and_permissions(make_actor, make_property):
    owner, verifier, other = make_actor(), make_actor("verifier"), make_actor()
    prop = make_property(owner)
    request = _submit(owner, prop).json()
    url = f"/api/v1/verification/{request['id']}/decision"
    decision = {"decision": "approved", "notes": "Documents reviewed"}

    assert other.get("/api/v1/verification/queue").status_code == 403
    assert other.post(url, json=decision).status_code == 403
    assert owner.post(url, json=decision).status_code == 403
    assert verifier.get("/api/v1/verification/queue").json()["total"] == 1
    assert verifier.get(f"/api/v1/properties/{prop['id']}").json()["access_level"] == "full"
    assert verifier.get(f"/api/v1/properties/{prop['id']}/documents").status_code == 200

    decided = verifier.post(url, json=decision)
    assert decided.status_code == 200 and decided.json()["reviewed_by_id"] == verifier.user["id"]
    assert verifier.post(url, json=decision).status_code == 409
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["verification_status"] == "verified"
    assert owner.get("/api/v1/notifications").json()["total"] == 1


def test_verifier_cannot_review_own_property(make_actor, make_property):
    verifier = make_actor("verifier")
    request = _submit(verifier, make_property(verifier)).json()
    response = verifier.post(f"/api/v1/verification/{request['id']}/decision", json={"decision": "approved", "notes": "looks fine"})
    assert response.status_code == 403 and response.json()["error"]["code"] == "conflict_of_interest"


def test_editing_verified_fields_resets_verification(make_actor, make_property):
    owner, verifier = make_actor(), make_actor("verifier")
    prop = make_property(owner)
    request = _submit(owner, prop).json()
    verifier.post(f"/api/v1/verification/{request['id']}/decision", json={"decision": "approved", "notes": "reviewed"})
    url = f"/api/v1/properties/{prop['id']}"
    assert owner.patch(url, json={"description": "New paint"}).json()["verification_status"] == "verified"
    assert owner.patch(url, json={"address_line1": "Elsewhere 1"}).json()["verification_status"] == "unverified"


def test_report_flow(make_actor, make_property):
    owner, reporter, admin = make_actor(), make_actor(), make_actor("admin")
    prop = make_property(owner, listing_status="listed")
    url = f"/api/v1/properties/{prop['id']}/report"
    assert owner.post(url, json={"reason": "my own listing"}).status_code == 422
    report = reporter.post(url, json={"reason": "This looks fake"}).json()
    assert reporter.get("/api/v1/admin/reports").status_code == 403
    assert admin.patch(f"/api/v1/admin/reports/{report['id']}", json={"status": "actioned", "archive_listing": True}).status_code == 200
    assert owner.get(f"/api/v1/properties/{prop['id']}").json()["listing_status"] == "archived"

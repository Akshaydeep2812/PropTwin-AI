import os
import tempfile

os.environ["APP_ENV"] = "test"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["WORKER_ENABLED"] = "false"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="proptwin-test-")
os.environ["SMTP_HOST"] = ""

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.services import auth_service, valuation_service

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PASSWORD = "correct-horse-battery"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _engine():
    if TEST_DATABASE_URL:
        return create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    event.listen(engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    return engine


@pytest.fixture
def session_factory():
    engine = _engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def client(session_factory):
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"X-Requested-With": "XMLHttpRequest"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class Actor:
    def __init__(self, client: TestClient, token: str, user: dict):
        self.client, self.token, self.user = client, token, user

    def request(self, method: str, url: str, **kwargs):
        # Requests are sent as this actor only; the shared client's cookie jar stays out of it.
        self.client.cookies.clear()
        return self.client.request(method, url, headers={"Authorization": f"Bearer {self.token}"}, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def patch(self, url, **kw):
        return self.request("PATCH", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


@pytest.fixture
def make_actor(client, session_factory):
    counter = {"n": 0}

    def make(role: str = "owner", email: str | None = None) -> Actor:
        counter["n"] += 1
        email = email or f"{role}{counter['n']}@example.com"
        if role in ("owner", "investor"):
            response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": role.title(), "role": role})
            assert response.status_code == 201, response.text
        else:
            # Privileged roles cannot be self-assigned, so tests grant them directly as an operator would.
            with session_factory() as session:
                user = auth_service.register_user(session, email, PASSWORD, role.title(), "owner")
                user.roles.append(auth_service.get_role(session, role))
                session.commit()
            response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert response.status_code == 200, response.text
        body = response.json()
        client.cookies.clear()
        return Actor(client, body["access_token"], body["user"])

    return make


@pytest.fixture(scope="session")
def trained_artifacts(tmp_path_factory):
    """A real, small model trained by the real pipeline, so inference tests never rely on a mocked network."""
    output = tmp_path_factory.mktemp("artifacts")
    data = output.parent / "tiny.csv"
    scripts = REPO_ROOT / "ml" / "scripts"
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    subprocess.run([sys.executable, str(scripts / "generate_dataset.py"), "--rows", "1500", "--output", str(data)], check=True, env=env, capture_output=True)
    subprocess.run([sys.executable, str(scripts / "train.py"), "--data", str(data), "--output", str(output), "--version", "test-model", "--max-epochs", "40"], check=True, env=env, capture_output=True)
    return output


@pytest.fixture
def artifact_dir(trained_artifacts, monkeypatch):
    monkeypatch.setattr(get_settings(), "model_artifact_dir", trained_artifacts)
    return trained_artifacts


@pytest.fixture
def active_model(artifact_dir, db):
    """Registers and activates the test model directly, bypassing the promotion gate tested elsewhere."""
    valuation_service.sync_artifacts(db)
    record = valuation_service.get_model_record(db, "test-model")
    record.status = "active"
    db.commit()
    return record


PROPERTY = {
    "title": "Test apartment",
    "property_type": "apartment",
    "address_line1": "12 Private Street",
    "locality": "Riverside",
    "city": "Demo City",
    "state": "Demo State",
    "postal_code": "500001",
    "built_up_area_sqft": "1200.00",
    "bedrooms": 2,
    "bathrooms": 2,
    "construction_year": 2015,
    "condition": "good",
    "amenities": ["Gym", " lift "],
    "parking_spaces": 1,
    "asking_price": "7500000.00",
    "monthly_rent": "25000.00",
    "last_sale_price": "6000000.00",
    "last_sale_date": "2020-01-15",
}


@pytest.fixture
def property_payload():
    return dict(PROPERTY)


@pytest.fixture
def make_property(property_payload):
    def make(actor: Actor, **overrides) -> dict:
        response = actor.post("/api/v1/properties", json={**property_payload, **overrides})
        assert response.status_code == 201, response.text
        return response.json()

    return make

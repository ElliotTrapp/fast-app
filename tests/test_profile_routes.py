"""Tests for profile API routes.

Integration tests for FastAPI profile endpoints using TestClient.
Tests CRUD operations, default profile management, import/export,
and auth-disabled mode.

Uses a standalone FastAPI app with only the profile router to avoid
lifecycle/middleware conflicts from the main app.

Required deps: pip install -e ".[auth]"
"""

import pytest

sqlmodel = pytest.importorskip(  # noqa: E402
    "sqlmodel", reason="auth deps not installed - pip install -e '.[auth]'"
)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from fast_app.db import get_session  # noqa: E402
from fast_app.models.db_models import User  # noqa: E402
from fast_app.services.auth import get_current_user, hash_password  # noqa: E402
from fast_app.webapp.profile_routes import router as profile_router  # noqa: E402


def _make_profile_data(name="Test Profile", is_default=False):
    """Create a profile payload for POST requests."""
    return {
        "name": name,
        "profile_data": {"name": "Test User", "skills": ["Python"]},
        "is_default": is_default,
    }


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with all tables."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """Provide a database session for tests."""
    with Session(engine) as sess:
        yield sess


@pytest.fixture
def test_user(session):
    """Create and return a test user."""
    user = User(email="test@example.com", hashed_password=hash_password("password"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def app_client(engine, session, test_user):
    """Create a test app with DB session and auth overrides."""
    from fast_app.config import Config

    test_app = FastAPI()
    test_app.include_router(profile_router)

    def get_session_override():
        yield session

    async def get_current_user_override():
        return test_user

    test_app.dependency_overrides[get_session] = get_session_override
    test_app.dependency_overrides[get_current_user] = get_current_user_override
    test_app.dependency_overrides[Config] = lambda: None

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


@pytest.fixture
def disabled_app_client(engine, session):
    """Create a test app with auth disabled (get_current_user returns None)."""
    from fast_app.config import Config

    test_app = FastAPI()
    test_app.include_router(profile_router)

    def get_session_override():
        yield session

    async def get_current_user_disabled():
        return None

    test_app.dependency_overrides[get_session] = get_session_override
    test_app.dependency_overrides[get_current_user] = get_current_user_disabled
    test_app.dependency_overrides[Config] = lambda: None

    with TestClient(test_app) as client:
        yield client

    test_app.dependency_overrides.clear()


class TestCreateProfile:
    def test_create_profile_returns_201(self, app_client):
        response = app_client.post("/api/profiles", json=_make_profile_data())
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Profile"
        assert data["profile_data"] == {
            "name": "Test User",
            "skills": ["Python"],
        }
        assert data["is_default"] is False
        assert "id" in data

    def test_create_default_profile_unsets_existing(self, app_client):
        first = _make_profile_data(name="First", is_default=True)
        app_client.post("/api/profiles", json=first)

        second = _make_profile_data(name="Second", is_default=True)
        response = app_client.post("/api/profiles", json=second)
        assert response.status_code == 201

        # Verify only the second is default
        profiles = app_client.get("/api/profiles").json()
        defaults = [p for p in profiles if p["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["name"] == "Second"


class TestListProfiles:
    def test_list_profiles_returns_empty(self, app_client):
        response = app_client.get("/api/profiles")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_profiles_returns_created(self, app_client):
        app_client.post("/api/profiles", json=_make_profile_data())

        response = app_client.get("/api/profiles")
        assert response.status_code == 200
        profiles = response.json()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Test Profile"


class TestGetProfile:
    def test_get_profile_returns_200(self, app_client):
        create_resp = app_client.post("/api/profiles", json=_make_profile_data())
        profile_id = create_resp.json()["id"]

        response = app_client.get(f"/api/profiles/{profile_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Test Profile"

    def test_get_profile_returns_404_if_not_found(self, app_client):
        response = app_client.get("/api/profiles/9999")
        assert response.status_code == 404


class TestUpdateProfile:
    def test_update_profile_returns_200(self, app_client):
        create_resp = app_client.post("/api/profiles", json=_make_profile_data())
        profile_id = create_resp.json()["id"]

        update_data = {
            "name": "Updated",
            "profile_data": {"name": "New Name"},
            "is_default": False,
        }
        response = app_client.put(f"/api/profiles/{profile_id}", json=update_data)
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"
        assert response.json()["profile_data"] == {"name": "New Name"}

    def test_update_profile_returns_404_if_not_found(self, app_client):
        update_data = {"name": "X", "profile_data": {}, "is_default": False}
        response = app_client.put("/api/profiles/9999", json=update_data)
        assert response.status_code == 404


class TestDeleteProfile:
    def test_delete_profile_returns_204(self, app_client):
        create_resp = app_client.post("/api/profiles", json=_make_profile_data())
        profile_id = create_resp.json()["id"]

        response = app_client.delete(f"/api/profiles/{profile_id}")
        assert response.status_code == 204

        # Verify deleted
        get_resp = app_client.get(f"/api/profiles/{profile_id}")
        assert get_resp.status_code == 404

    def test_delete_profile_returns_404_if_not_found(self, app_client):
        response = app_client.delete("/api/profiles/9999")
        assert response.status_code == 404


class TestGetDefaultProfile:
    def test_get_default_profile_returns_200(self, app_client):
        data = _make_profile_data(name="Default", is_default=True)
        app_client.post("/api/profiles", json=data)

        response = app_client.get("/api/profiles/default")
        assert response.status_code == 200
        assert response.json()["is_default"] is True

    def test_get_default_profile_returns_404_if_none(self, app_client):
        response = app_client.get("/api/profiles/default")
        assert response.status_code == 404


class TestImportProfile:
    def test_import_profile_returns_201(self, app_client):
        import_data = {
            "name": "Imported",
            "profile_data": {"name": "Imported User"},
            "is_default": False,
        }
        response = app_client.post("/api/profiles/import", json=import_data)
        assert response.status_code == 201
        assert response.json()["name"] == "Imported"


class TestExportProfile:
    def test_export_profile_returns_200(self, app_client):
        create_resp = app_client.post("/api/profiles", json=_make_profile_data())
        profile_id = create_resp.json()["id"]

        response = app_client.get(f"/api/profiles/{profile_id}/export")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Profile"
        assert data["profile_data"] == {
            "name": "Test User",
            "skills": ["Python"],
        }

    def test_export_profile_returns_404_if_not_found(self, app_client):
        response = app_client.get("/api/profiles/9999/export")
        assert response.status_code == 404


class TestAuthDisabledMode:
    """Test profile routes in auth-disabled mode (get_current_user returns None)."""

    def test_create_profile_without_auth(self, disabled_app_client):
        data = _make_profile_data()
        response = disabled_app_client.post("/api/profiles", json=data)
        assert response.status_code == 201

    def test_list_profiles_without_auth(self, disabled_app_client):
        response = disabled_app_client.get("/api/profiles")
        assert response.status_code == 200

    def test_get_default_profile_without_auth(self, disabled_app_client):
        response = disabled_app_client.get("/api/profiles/default")
        # No default set yet, should be 404
        assert response.status_code == 404

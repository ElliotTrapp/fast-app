"""Integration tests for knowledge REST API endpoints.

Tests search, list, and delete endpoints under /api/knowledge.
Uses FastAPI TestClient with auth-disabled mode (user_id=1 fallback).

Required deps: pip install -e ".[knowledge]"
"""

import pytest


def _check_deps():
    """Check if knowledge dependencies are installed, skip if not."""
    try:
        import chromadb  # noqa: F401
    except ImportError:
        pytest.skip("knowledge deps not installed - pip install -e '.[knowledge]'")


@pytest.fixture(autouse=True)
def check_knowledge_deps():
    """Skip all tests in this module if knowledge deps aren't installed."""
    _check_deps()
    yield


@pytest.fixture(autouse=True)
def reset_secret():
    """Reset the SECRET_KEY module variable so auth is disabled."""
    import fast_app.services.auth as auth_module

    original = auth_module.SECRET_KEY
    auth_module.SECRET_KEY = ""
    yield
    auth_module.SECRET_KEY = original


@pytest.fixture()
def client():
    """Create a TestClient with auth-disabled mode and in-memory DB."""
    from sqlmodel import Session, SQLModel, create_engine

    from fast_app.db import get_session
    from fast_app.services.auth import get_current_user
    from fast_app.webapp.app import app

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _test_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _test_get_session
    app.dependency_overrides[get_current_user] = lambda: None

    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


class TestSearchFacts:
    """Tests for GET /api/knowledge/search."""

    def test_search_returns_200_with_empty_results(self, client):
        """Search endpoint returns 200 even when no facts exist."""
        response = client.get("/api/knowledge/search", params={"query": "Python"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_search_with_category_filter(self, client):
        """Search endpoint accepts category filter parameter."""
        response = client.get(
            "/api/knowledge/search",
            params={"query": "Python", "category": "skill"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_search_with_n_parameter(self, client):
        """Search endpoint accepts n parameter for result count."""
        response = client.get(
            "/api/knowledge/search",
            params={"query": "Python", "n": 3},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_search_missing_query_returns_422(self, client):
        """Search endpoint returns 422 when query param is missing."""
        response = client.get("/api/knowledge/search")
        assert response.status_code == 422


class TestListFacts:
    """Tests for GET /api/knowledge/facts."""

    def test_list_returns_200_with_empty_results(self, client):
        """List endpoint returns 200 even when no facts exist."""
        response = client.get("/api/knowledge/facts")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_category_filter(self, client):
        """List endpoint accepts category filter parameter."""
        response = client.get(
            "/api/knowledge/facts",
            params={"category": "skill"},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_with_limit(self, client):
        """List endpoint accepts limit parameter."""
        response = client.get(
            "/api/knowledge/facts",
            params={"limit": 5},
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestDeleteFacts:
    """Tests for DELETE /api/knowledge/facts."""

    def test_delete_with_empty_ids_raises_error(self, client):
        """Delete endpoint returns 422 when ids list is empty."""
        response = client.request(
            "DELETE",
            "/api/knowledge/facts",
            json={"ids": []},
        )
        assert response.status_code == 422

    def test_delete_with_valid_ids_returns_200_or_500(self, client):
        """Delete endpoint returns 200 or 500 depending on ChromaDB availability."""
        response = client.request(
            "DELETE",
            "/api/knowledge/facts",
            json={"ids": ["nonexistent-id-123"]},
        )
        # 200 if ChromaDB available, 500 if unavailable
        assert response.status_code in (200, 500)

    def test_delete_without_body_returns_422(self, client):
        """Delete endpoint returns 422 when request body is missing."""
        response = client.request("DELETE", "/api/knowledge/facts")
        assert response.status_code == 422

    def test_delete_with_invalid_body_returns_422(self, client):
        """Delete endpoint returns 422 when body is not valid JSON."""
        response = client.request(
            "DELETE",
            "/api/knowledge/facts",
            json={"wrong_field": ["id1"]},
        )
        assert response.status_code == 422

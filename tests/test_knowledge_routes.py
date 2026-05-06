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

    def test_delete_persists_across_service_instances(self, client):
        """Deleted facts must not reappear on subsequent list calls.

        Regression test for the ChromaDB PersistentClient caching bug:
        each request created a new KnowledgeService with a new PersistentClient,
        and deletions on one client were invisible to another client's cache.
        The fix caches PersistentClient instances at the class level.
        """
        create_resp = client.post(
            "/api/knowledge/facts",
            json={"content": "Fact to delete", "category": "test"},
        )
        assert create_resp.status_code == 201
        fact_id = create_resp.json()["id"]

        delete_resp = client.request(
            "DELETE",
            "/api/knowledge/facts",
            json={"ids": [fact_id]},
        )
        assert delete_resp.status_code == 200

        list_resp = client.get("/api/knowledge/facts")
        assert list_resp.status_code == 200
        remaining_ids = [f["id"] for f in list_resp.json()]
        assert fact_id not in remaining_ids


class TestAddFact:
    """Tests for POST /api/knowledge/facts."""

    def test_add_fact(self, client):
        """Add fact endpoint creates a fact and returns 201 with fact data."""
        response = client.post(
            "/api/knowledge/facts",
            json={
                "content": "5 years of Python experience",
                "category": "skill",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "5 years of Python experience"
        assert data["category"] == "skill"
        assert "id" in data
        assert "created_at" in data

    def test_add_fact_default_category(self, client):
        """Add fact defaults category to 'general' when not provided."""
        response = client.post(
            "/api/knowledge/facts",
            json={"content": "Some general fact"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["category"] == "general"


class TestUpdateFact:
    """Tests for PUT /api/knowledge/facts/{fact_id}."""

    def test_update_fact_content(self, client):
        """Update fact endpoint updates content and returns updated fact."""
        create_response = client.post(
            "/api/knowledge/facts",
            json={"content": "Original content", "category": "skill"},
        )
        assert create_response.status_code == 201
        fact_id = create_response.json()["id"]

        update_response = client.put(
            f"/api/knowledge/facts/{fact_id}",
            json={"content": "Updated content"},
        )
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["content"] == "Updated content"
        assert data["category"] == "skill"
        assert data["id"] != fact_id  # UUID changes on update

    def test_update_fact_not_found(self, client):
        """Update fact endpoint returns 404 for nonexistent fact ID."""
        response = client.put(
            "/api/knowledge/facts/nonexistent-id-12345",
            json={"content": "Updated content"},
        )
        assert response.status_code == 404


class TestGetCategories:
    """Tests for GET /api/knowledge/categories."""

    def test_get_categories(self, client):
        """Get categories endpoint returns list of unique categories."""
        client.post(
            "/api/knowledge/facts",
            json={"content": "Python skill", "category": "skill"},
        )
        client.post(
            "/api/knowledge/facts",
            json={"content": "Work experience", "category": "experience"},
        )

        response = client.get("/api/knowledge/categories")
        assert response.status_code == 200
        categories = response.json()
        assert isinstance(categories, list)
        assert "skill" in categories
        assert "experience" in categories

    def test_get_categories_empty(self, client):
        """Get categories returns a list even when no facts were added in this test."""
        response = client.get("/api/knowledge/categories")
        assert response.status_code == 200
        categories = response.json()
        assert isinstance(categories, list)

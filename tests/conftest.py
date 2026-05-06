"""Shared test fixtures for fast-app test suite."""

from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

from fast_app.config import (
    AuthConfig,
    ChromaConfig,
    Config,
    DatabaseConfig,
    LLMConfig,
    OllamaConfig,
)
from fast_app.db import get_session
from fast_app.services.auth import get_current_user
from fast_app.webapp.app import app


@pytest.fixture()
def client():
    """Create a TestClient with auth-disabled mode and in-memory DB.

    This fixture:
    - Creates an in-memory SQLite database
    - Overrides get_session to use the test DB
    - Overrides get_current_user to disable auth
    - Patches knowledge service factory for consistent test config
    - Cleans up dependency overrides after the test
    """
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    def _test_get_session():
        with Session(engine) as session:
            yield session

    test_config = Config(
        ollama=OllamaConfig(),
        database=DatabaseConfig(),
        auth=AuthConfig(),
        llm=LLMConfig(),
        chroma=ChromaConfig(),
    )

    def _test_get_service(user_id: int):
        from fast_app.services.knowledge import KnowledgeService

        return KnowledgeService(test_config, user_id)

    app.dependency_overrides[get_session] = _test_get_session
    app.dependency_overrides[get_current_user] = lambda: None

    with patch("fast_app.webapp.knowledge_routes._get_service", _test_get_service):
        from fastapi.testclient import TestClient

        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_secret():
    """Reset the JWT_SECRET module variable so auth is disabled."""
    import fast_app.services.auth_core as auth_module

    original = auth_module.JWT_SECRET
    auth_module.JWT_SECRET = ""
    yield
    auth_module.JWT_SECRET = original


@pytest.fixture(autouse=True)
def reset_knowledge_client_cache():
    """Reset the KnowledgeService client cache between tests."""
    from fast_app.services.knowledge import KnowledgeService

    yield
    KnowledgeService.reset_client_cache()

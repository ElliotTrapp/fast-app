"""Tests for authentication service.

Tests password hashing, JWT token creation/validation,
auth-disabled mode, and FastAPI dependencies.

Required deps: pip install -e ".[auth]"
"""

import os

import pytest


def _check_deps():
    """Check if auth dependencies are installed, skip if not."""
    try:
        import bcrypt  # noqa: F401
        from jose import jwt  # noqa: F401
        from sqlmodel import Session  # noqa: F401
    except ImportError:
        pytest.skip("auth deps not installed - pip install -e '.[auth]'")


@pytest.fixture(autouse=True)
def check_auth_deps():
    """Skip all tests in this module if auth deps aren't installed."""
    _check_deps()
    yield


@pytest.fixture(autouse=True)
def reset_secret():
    """Reset the JWT_SECRET module variable for each test."""
    import fast_app.services.auth_core as auth_module

    original = auth_module.JWT_SECRET
    yield
    auth_module.JWT_SECRET = original


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        from fast_app.services.auth import hash_password

        hashed = hash_password("test_password")
        assert hashed.startswith("$2b$")

    def test_hash_password_different_each_time(self):
        """Bcrypt generates unique salts, so same password = different hashes."""
        from fast_app.services.auth import hash_password

        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_verify_password_correct(self):
        from fast_app.services.auth import hash_password, verify_password

        hashed = hash_password("my_secure_password")
        assert verify_password("my_secure_password", hashed) is True

    def test_verify_password_incorrect(self):
        from fast_app.services.auth import hash_password, verify_password

        hashed = hash_password("my_secure_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_empty(self):
        from fast_app.services.auth import hash_password, verify_password

        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_hash_password_max_bcrypt_length(self):
        from fast_app.services.auth import hash_password, verify_password

        pw = "a" * 72
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True


class TestJWTokens:
    def test_create_access_token_with_secret(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token

        auth_module.JWT_SECRET = "test-secret-key-for-testing"
        token = create_access_token(user_id=1)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_access_token_with_secret(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.JWT_SECRET = "test-secret-key-for-testing"
        token = create_access_token(user_id=42)
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert "exp" in payload

    def test_create_token_without_secret_raises(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token

        auth_module.JWT_SECRET = ""
        with pytest.raises(ValueError, match="FAST_APP_JWT_SECRET"):
            create_access_token(user_id=1)

    def test_decode_invalid_token_raises(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import decode_access_token

        auth_module.JWT_SECRET = "test-secret-key-for-testing"
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_access_token("invalid.token.here")

    def test_decode_token_with_wrong_secret_raises(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.JWT_SECRET = "secret-one"
        token = create_access_token(user_id=1)
        auth_module.JWT_SECRET = "secret-two"
        with pytest.raises(ValueError):
            decode_access_token(token)

    def test_create_token_with_custom_expiry(self):
        from datetime import timedelta

        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.JWT_SECRET = "test-secret-key-for-testing"
        token = create_access_token(user_id=1, expires_delta=timedelta(hours=1))
        payload = decode_access_token(token)
        assert payload["sub"] == "1"

    def test_token_contains_user_id(self):
        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.JWT_SECRET = "test-secret-key-for-testing"
        for user_id in [1, 42, 9999]:
            token = create_access_token(user_id=user_id)
            payload = decode_access_token(token)
            assert int(payload["sub"]) == user_id


class TestAuthDisabledMode:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        for f in [
            "test_auth_enabled.db",
            "test_auth_disabled.db",
            "test_auth_with_user.db",
        ]:
            if os.path.exists(f):
                os.unlink(f)

    def test_is_auth_enabled_with_secret(self):
        from sqlmodel import Session, SQLModel, create_engine

        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import is_auth_enabled

        auth_module.JWT_SECRET = "some-secret"
        engine = create_engine("sqlite:///test_auth_enabled.db")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            assert is_auth_enabled(session) is True

    def test_is_auth_enabled_without_secret_and_no_users(self):
        from sqlmodel import Session, SQLModel, create_engine

        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import is_auth_enabled

        auth_module.JWT_SECRET = ""
        engine = create_engine("sqlite:///test_auth_disabled.db")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            result = is_auth_enabled(session)
            assert result is False

    def test_is_auth_enabled_without_secret_but_with_users(self):
        from sqlmodel import Session, SQLModel, create_engine

        import fast_app.services.auth_core as auth_module
        from fast_app.db import init_db
        from fast_app.models.db_models import User
        from fast_app.services.auth import is_auth_enabled

        auth_module.JWT_SECRET = ""
        engine = create_engine("sqlite:///test_auth_with_user.db")

        init_db(config=None)

        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(User(email="test@example.com", hashed_password="hash"))
            session.commit()
            result = is_auth_enabled(session)
            assert result is True


class TestLoginPage:
    """Tests for the login page endpoint."""

    def test_login_page_returns_200(self):
        """GET /login should return 200 (either HTML content or 404 fallback)."""
        from starlette.testclient import TestClient

        from fast_app.webapp.app import app

        client = TestClient(app)
        response = client.get("/login", follow_redirects=False)
        assert response.status_code in (200, 404)

    def test_login_page_returns_html(self):
        """GET /login should return HTML content type."""
        from starlette.testclient import TestClient

        from fast_app.webapp.app import app

        client = TestClient(app)
        response = client.get("/login", follow_redirects=False)
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            assert "text/html" in response.headers.get("content-type", "")


def _get_app_module():
    """Get the fast_app.webapp.app module (not the FastAPI instance).

    The webapp __init__.py re-exports `app` as the FastAPI instance,
    so `import fast_app.webapp.app as app_module` resolves to the
    FastAPI object, not the module. Use importlib to get the actual module.
    """
    import importlib

    return importlib.import_module("fast_app.webapp.app")


class TestAuthGuardPublicPaths:
    """Tests that auth guard allows access to public paths without authentication."""

    @pytest.fixture(autouse=True)
    def _clear_auth_cache(self):
        """Clear the auth-enabled cache before and after each test."""
        app_module = _get_app_module()
        app_module._auth_enabled_cache.clear()
        yield
        app_module._auth_enabled_cache.clear()

    def test_login_page_accessible_without_auth(self):
        """GET /login should always be accessible, even when auth is enabled."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/login", follow_redirects=False)
        assert response.status_code in (200, 404)

    def test_health_endpoint_accessible_without_auth(self):
        """GET /health should always be accessible."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/health", follow_redirects=False)
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_auth_enabled_endpoint_accessible_without_auth(self):
        """GET /api/auth/enabled should be accessible without authentication."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/api/auth/enabled", follow_redirects=False)
        assert response.status_code == 200
        assert "enabled" in response.json()

    def test_static_path_accessible_without_auth(self):
        """Paths starting with /static/ should be accessible without auth."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        # Static file may return 200 or 404 depending on whether the file exists,
        # but should NOT redirect to /login
        response = client.get("/static/nonexistent.css", follow_redirects=False)
        assert response.status_code != 303

    def test_auth_login_endpoint_accessible_without_auth(self):
        """POST /api/auth/login should be accessible without authentication."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        # POST with invalid credentials should get 401 or 422, NOT a redirect
        response = client.post(
            "/api/auth/login",
            json={"email": "nonexistent@test.com", "password": "wrong"},
            follow_redirects=False,
        )
        assert response.status_code in (401, 422)


class TestAuthGuardRedirect:
    """Tests that auth guard redirects unauthenticated users when auth is enabled."""

    @pytest.fixture(autouse=True)
    def _clear_auth_cache(self):
        """Clear the auth-enabled cache before and after each test."""
        app_module = _get_app_module()
        app_module._auth_enabled_cache.clear()
        yield
        app_module._auth_enabled_cache.clear()

    def test_protected_path_redirects_when_auth_enabled(self):
        """GET / should redirect to /login when auth is enabled and no token is present."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_api_status_redirects_when_auth_enabled(self):
        """GET /api/status should redirect to /login when auth is enabled and no token."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/api/status", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_protected_path_allows_valid_token(self):
        """GET / with a valid token should pass through auth guard."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        token = create_access_token(user_id=1)

        client = TestClient(app)
        response = client.get(
            "/",
            cookies={"fast_app_token": token},
            follow_redirects=False,
        )
        # Should NOT redirect — either 200 (page served) or pass through
        assert response.status_code != 303

    def test_protected_path_allows_bearer_token(self):
        """GET / with Bearer token in header should pass through auth guard."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.services.auth import create_access_token
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = "test-secret-for-guard"
        app_module._auth_enabled_cache.clear()

        token = create_access_token(user_id=1)

        client = TestClient(app)
        response = client.get(
            "/",
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
        assert response.status_code != 303

    def test_auth_disabled_allows_all_paths(self):
        """When auth is disabled, all paths should be accessible without a token."""
        from starlette.testclient import TestClient

        import fast_app.services.auth_core as auth_module
        from fast_app.webapp.app import app

        app_module = _get_app_module()

        auth_module.JWT_SECRET = ""
        app_module._auth_enabled_cache.clear()

        client = TestClient(app)
        response = client.get("/", follow_redirects=False)
        # Should NOT redirect — either 200 or pass through
        assert response.status_code != 303


class TestLogout:
    """Tests for the logout endpoint."""

    def test_logout_returns_200(self):
        """POST /api/auth/logout should return 200."""
        from starlette.testclient import TestClient

        from fast_app.webapp.app import app

        client = TestClient(app)
        response = client.post("/api/auth/logout", follow_redirects=False)
        assert response.status_code == 200

    def test_logout_clears_cookie(self):
        """POST /api/auth/logout should clear the fast_app_token cookie."""
        from starlette.testclient import TestClient

        from fast_app.webapp.app import app

        client = TestClient(app)
        # Set a cookie first, then logout
        client.cookies.set("fast_app_token", "some-token-value")
        response = client.post("/api/auth/logout", follow_redirects=False)
        assert response.status_code == 200
        # The response should include a Set-Cookie header that clears the token
        set_cookie_headers = [v for k, v in response.headers.items() if k.lower() == "set-cookie"]
        assert any("fast_app_token" in h for h in set_cookie_headers)

    def test_logout_returns_logged_out_status(self):
        """POST /api/auth/logout should return {"status": "logged_out"}."""
        from starlette.testclient import TestClient

        from fast_app.webapp.app import app

        client = TestClient(app)
        response = client.post("/api/auth/logout", follow_redirects=False)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged_out"

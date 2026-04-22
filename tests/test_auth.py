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
    """Reset the SECRET_KEY module variable for each test."""
    import fast_app.services.auth as auth_module

    original = auth_module.SECRET_KEY
    yield
    auth_module.SECRET_KEY = original


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
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token

        auth_module.SECRET_KEY = "test-secret-key-for-testing"
        token = create_access_token(user_id=1)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_access_token_with_secret(self):
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.SECRET_KEY = "test-secret-key-for-testing"
        token = create_access_token(user_id=42)
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert "exp" in payload

    def test_create_token_without_secret_raises(self):
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token

        auth_module.SECRET_KEY = ""
        with pytest.raises(ValueError, match="FAST_APP_JWT_SECRET"):
            create_access_token(user_id=1)

    def test_decode_invalid_token_raises(self):
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import decode_access_token

        auth_module.SECRET_KEY = "test-secret-key-for-testing"
        with pytest.raises(ValueError, match="Invalid or expired token"):
            decode_access_token("invalid.token.here")

    def test_decode_token_with_wrong_secret_raises(self):
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.SECRET_KEY = "secret-one"
        token = create_access_token(user_id=1)
        auth_module.SECRET_KEY = "secret-two"
        with pytest.raises(ValueError):
            decode_access_token(token)

    def test_create_token_with_custom_expiry(self):
        from datetime import timedelta

        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.SECRET_KEY = "test-secret-key-for-testing"
        token = create_access_token(user_id=1, expires_delta=timedelta(hours=1))
        payload = decode_access_token(token)
        assert payload["sub"] == "1"

    def test_token_contains_user_id(self):
        import fast_app.services.auth as auth_module
        from fast_app.services.auth import create_access_token, decode_access_token

        auth_module.SECRET_KEY = "test-secret-key-for-testing"
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

        import fast_app.services.auth as auth_module
        from fast_app.services.auth import is_auth_enabled

        auth_module.SECRET_KEY = "some-secret"
        engine = create_engine("sqlite:///test_auth_enabled.db")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            assert is_auth_enabled(session) is True

    def test_is_auth_enabled_without_secret_and_no_users(self):
        from sqlmodel import Session, SQLModel, create_engine

        import fast_app.services.auth as auth_module
        from fast_app.services.auth import is_auth_enabled

        auth_module.SECRET_KEY = ""
        engine = create_engine("sqlite:///test_auth_disabled.db")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            result = is_auth_enabled(session)
            assert result is False

    def test_is_auth_enabled_without_secret_but_with_users(self):
        from sqlmodel import Session, SQLModel, create_engine

        import fast_app.services.auth as auth_module
        from fast_app.db import init_db
        from fast_app.models.db_models import User
        from fast_app.services.auth import is_auth_enabled

        auth_module.SECRET_KEY = ""
        engine = create_engine("sqlite:///test_auth_with_user.db")

        init_db(config=None)

        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(User(email="test@example.com", hashed_password="hash"))
            session.commit()
            result = is_auth_enabled(session)
            assert result is True

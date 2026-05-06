"""Core authentication logic for Fast-App.

This module provides password hashing, JWT token creation/validation, and
auth-enabled detection — without any FastAPI dependencies. It can be used
by both the CLI and the webapp without importing FastAPI.

## Usage

    from .auth_core import hash_password, verify_password, create_access_token, decode_access_token

## Dependencies

Requires the [auth] extra: pip install -e ".[auth]"
Imports bcrypt, jose, and sqlmodel lazily to allow graceful degradation.

See: docs/adr/004-jwt-bcrypt-auth.md
"""

import os
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.environ.get("FAST_APP_JWT_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("FAST_APP_JWT_EXPIRE_MINUTES", "1440"))

# Lazy imports for optional dependencies
_bcrypt = None
_jose = None
_sqlmodel = None


def _get_bcrypt():
    """Lazily import bcrypt, raising ImportError if not installed."""
    global _bcrypt
    if _bcrypt is None:
        try:
            import bcrypt

            _bcrypt = bcrypt
        except ImportError as e:
            raise ImportError(
                'bcrypt is required for authentication. Install with: pip install -e ".[auth]"'
            ) from e
    return _bcrypt


def _get_jose():
    """Lazily import jose, raising ImportError if not installed."""
    global _jose
    if _jose is None:
        try:
            from jose import JWTError, jwt

            _jose = (JWTError, jwt)
        except ImportError as e:
            raise ImportError(
                'python-jose is required for authentication. Install with: pip install -e ".[auth]"'
            ) from e
    return _jose


def _get_sqlmodel():
    """Lazily import sqlmodel, raising ImportError if not installed."""
    global _sqlmodel
    if _sqlmodel is None:
        try:
            from sqlmodel import Session, select

            _sqlmodel = (Session, select)
        except ImportError as e:
            raise ImportError(
                'sqlmodel is required for authentication. Install with: pip install -e ".[auth]"'
            ) from e
    return _sqlmodel


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with cost factor 12."""
    bcrypt = _get_bcrypt()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    bcrypt = _get_bcrypt()
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token for a user.

    Args:
        user_id: The user's database ID to encode in the token.
        expires_delta: Optional custom expiration time. Defaults to
            ACCESS_TOKEN_EXPIRE_MINUTES (24 hours).

    Returns:
        The encoded JWT token string.

    Raises:
        ValueError: If FAST_APP_JWT_SECRET is not set.
    """
    if not JWT_SECRET:
        raise ValueError(
            "FAST_APP_JWT_SECRET must be set for authentication. "
            'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    jwt_error_cls, jwt = _get_jose()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode.

    Returns:
        The token payload dict containing "sub" (user_id) and "exp" (expiration).

    Raises:
        ValueError: If the token is invalid, expired, or the secret is missing.
    """
    if not JWT_SECRET:
        raise ValueError("FAST_APP_JWT_SECRET must be set for authentication.")

    jwt_error_cls, jwt = _get_jose()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except jwt_error_cls as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def is_auth_enabled(session) -> bool:
    """Check if authentication is enabled.

    Auth is enabled when:
    1. FAST_APP_JWT_SECRET is set, OR
    2. Users exist in the database

    Args:
        session: A SQLModel Session to query for existing users.

    Returns:
        True if auth should be enforced, False if running in auth-disabled mode.
    """
    if JWT_SECRET:
        return True

    _, select = _get_sqlmodel()
    from ..models.db_models import User

    statement = select(User).limit(1)
    user = session.exec(statement).first()
    return user is not None


__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "is_auth_enabled",
    "JWT_SECRET",
    "ALGORITHM",
]

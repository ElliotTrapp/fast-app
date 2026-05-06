"""FastAPI authentication dependencies for Fast-App.

This module provides the FastAPI-specific authentication layer:
OAuth2 scheme, session dependency, and the get_current_user dependency.

Core auth logic (password hashing, JWT token management, auth detection)
lives in auth_core.py and has no FastAPI dependencies, making it usable
by both the CLI and the webapp.

See: auth_core.py, docs/adr/004-jwt-bcrypt-auth.md, docs/guide/auth-setup.md
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .auth_core import (
    ALGORITHM,
    JWT_SECRET,
    create_access_token,
    decode_access_token,
    hash_password,
    is_auth_enabled,
    verify_password,
)

if TYPE_CHECKING:
    from sqlmodel import Session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _session_dependency() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session.

    Lazily imports to avoid requiring sqlmodel at module level
    (sqlmodel is an optional [auth] dependency).
    """
    from ..db import get_session

    yield from get_session()


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    session: Session = Depends(_session_dependency),
) -> User | None:
    """FastAPI dependency that extracts and validates the current user from a JWT.

    Behavior:
    - If auth is disabled (no secret, no users): returns None
    - If auth is enabled and token is valid: returns the User object
    - If auth is enabled and token is invalid: raises HTTPException(401)

    Args:
        token: JWT token from Authorization header (or None).
        session: Database session from dependency injection.

    Returns:
        User object if authenticated, None if auth is disabled.

    Raises:
        HTTPException: 401 if auth is enabled and token is invalid/expired.
    """
    if not is_auth_enabled(session):
        return None

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        user = session.get(User, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# Import User for type hints
from ..db import get_session  # noqa: E402
from ..models.db_models import User  # noqa: E402

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "is_auth_enabled",
    "get_current_user",
    "get_session",
    "JWT_SECRET",
    "ALGORITHM",
]

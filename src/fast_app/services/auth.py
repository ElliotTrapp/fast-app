"""Authentication service for Fast-App.

This module provides password hashing, JWT token management, and FastAPI
authentication dependencies for multi-user support.

## Authentication Flow

1. **Signup**: POST /api/auth/signup → hash_password(password) → store in DB
   → create_access_token(user_id) → return token
2. **Login**: POST /api/auth/login → verify_password(password, hash) → if valid,
   create_access_token(user_id) → return token
3. **Authenticated request**: Authorization: Bearer <token> → decode_access_token(token)
   → get_current_user(token, session) → User object or 401

## Auth-Disabled Mode

When FAST_APP_JWT_SECRET is not set and no users exist in the database,
authentication is disabled. All endpoints work without tokens. This ensures
backward compatibility — existing single-user setups require zero changes.

When FAST_APP_JWT_SECRET is set OR users exist in the DB, auth is enabled and
protected endpoints require valid JWT tokens.

## Security Considerations

- Passwords are hashed with bcrypt (cost factor 12, ~400ms per hash)
- Timing attacks are prevented by hashing even for non-existent users
- JWT tokens are signed with HS256 using a configurable secret
- Tokens expire after 24 hours (configurable via FAST_APP_JWT_EXPIRE_MINUTES)
- Webapp tokens use httpOnly, Secure, SameSite=Strict cookies
- CLI tokens are stored in ~/.fast-app/auth.json with 0600 permissions

See: docs/adr/004-jwt-bcrypt-auth.md, docs/guide/auth-setup.md
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session

from ..db import get_session
from ..models.db_models import User

SECRET_KEY = os.environ.get("FAST_APP_JWT_SECRET", "")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("FAST_APP_JWT_EXPIRE_MINUTES", "1440"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with cost factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token for a user.

    The token contains the user ID as the "sub" (subject) claim and an
    expiration time. It is signed with the configured SECRET_KEY using HS256.

    Args:
        user_id: The user's database ID to encode in the token.
        expires_delta: Optional custom expiration time. Defaults to
            ACCESS_TOKEN_EXPIRE_MINUTES (24 hours).

    Returns:
        The encoded JWT token string.

    Raises:
        ValueError: If FAST_APP_JWT_SECRET is not set.

    Note:
        The SECRET_KEY must be set via the FAST_APP_JWT_SECRET environment
        variable. If not set, this function raises ValueError.
    """
    if not SECRET_KEY:
        raise ValueError(
            "FAST_APP_JWT_SECRET must be set for authentication. "
            'Generate one with: python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
        )

    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode.

    Returns:
        The token payload dict containing "sub" (user_id) and "exp" (expiration).

    Raises:
        ValueError: If the token is invalid, expired, or the secret is missing.
    """
    if not SECRET_KEY:
        raise ValueError("FAST_APP_JWT_SECRET must be set for authentication.")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise ValueError(f"Invalid or expired token: {e}") from e


def is_auth_enabled(session: Session) -> bool:
    """Check if authentication is enabled.

    Auth is enabled when:
    1. FAST_APP_JWT_SECRET is set, OR
    2. Users exist in the database

    Returns:
        True if auth should be enforced, False if running in auth-disabled mode.
    """
    if SECRET_KEY:
        return True

    from sqlmodel import select

    statement = select(User).limit(1)
    user = session.exec(statement).first()
    return user is not None


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    session: Session = Depends(get_session),
) -> User | None:
    """FastAPI dependency that extracts and validates the current user from a JWT.

    This dependency is used on protected endpoints:

        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user)):
            return {"email": user.email}

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
    except (ValueError, JWTError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

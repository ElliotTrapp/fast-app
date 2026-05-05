"""FastAPI authentication routes for user signup, login, and profile info.

This module defines the REST API endpoints for Fast-App's authentication system.
All routes are mounted under `/api/auth/` and follow the CLI-first architecture:
route handlers are thin wrappers that call the service layer.

## Endpoints

- POST /api/auth/signup — Create a new user account (returns JWT token)
- POST /api/auth/login — Authenticate existing user (returns JWT token)
- GET  /api/auth/me — Get current authenticated user info

## Auth-Disabled Mode

When FAST_APP_JWT_SECRET is not set and no users exist in the database,
authentication is disabled. All endpoints work without tokens.

When auth is enabled:
- /signup and /login always work (they create/verify credentials)
- /me requires a valid JWT token

## Token Delivery

- **Webapp**: Token is set as an httpOnly, Secure, SameSite=Strict cookie
- **CLI/API**: Token is returned in the response body for manual management

See: docs/adr/007-cli-first-architecture.md, docs/guide/auth-setup.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import select

from ..db import SessionDep
from ..models.db_models import User, UserCreate, UserRead
from ..services.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=dict)
async def signup(
    request: UserCreate,
    session: SessionDep,
) -> dict:
    """Create a new user account.

    Args:
        request: UserCreate schema with email and password.
        session: Database session from dependency injection.

    Returns:
        Dict with access_token and token_type.

    Raises:
        HTTPException: 400 if email is already registered.
        HTTPException: 422 if validation fails (empty email, short password).
    """
    existing = session.exec(select(User).where(User.email == request.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.post("/login", response_model=dict)
async def login(
    request: UserCreate,
    session: SessionDep,
    response: Response,
) -> dict:
    """Authenticate an existing user.

    Verifies email/password credentials and returns a JWT token.
    Also sets an httpOnly cookie for webapp use.

    Args:
        request: UserCreate schema with email and password.
        session: Database session from dependency injection.
        response: FastAPI Response object for setting cookies.

    Returns:
        Dict with access_token and token_type.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    user = session.exec(select(User).where(User.email == request.email)).first()

    if user is None:
        hash_password(request.password)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    token = create_access_token(user.id)

    if response is not None:
        response.set_cookie(
            key="fast_app_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    return {
        "access_token": token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserRead)
async def get_me(
    user: User | None = Depends(get_current_user),
) -> UserRead:
    """Get the current authenticated user.

    If auth is disabled, returns 401 (this endpoint requires authentication).
    If auth is enabled, returns the user associated with the Bearer token.

    Args:
        user: Current user from JWT token (injected by dependency).

    Returns:
        UserRead schema with user info (no password).

    Raises:
        HTTPException: 401 if not authenticated.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    return UserRead(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )

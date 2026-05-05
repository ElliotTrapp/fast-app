"""FastAPI profile routes for CRUD operations on user profiles.

This module defines the REST API endpoints for Fast-App's profile management.
All routes are mounted under `/api/profiles/` and follow the CLI-first architecture:
route handlers are thin wrappers that delegate to ProfileService.

## Endpoints

- GET    /api/profiles                    — List profiles for the current user
- POST   /api/profiles                    — Create a new profile
- GET    /api/profiles/{profile_id}       — Get a specific profile (owner check)
- PUT    /api/profiles/{profile_id}       — Update a profile (owner check)
- DELETE /api/profiles/{profile_id}       — Delete a profile (owner check)
- GET    /api/profiles/default             — Get the default profile
- POST   /api/profiles/import             — Import a profile from JSON data
- GET    /api/profiles/{profile_id}/export — Export a profile as JSON

## Auth-Disabled Mode

When FAST_APP_JWT_SECRET is not set and no users exist in the database,
authentication is disabled. In this mode, user_id defaults to 1 for all
operations, providing backward compatibility for single-user setups.

See: docs/adr/007-cli-first-architecture.md, docs/guide/profiles.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..models.db_models import ProfileCreate, ProfileRead, User, UserProfile
from ..services.auth import get_current_user
from ..services.profile_service import ProfileService

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

_service = ProfileService()

# Fallback user ID when auth is disabled
_DEFAULT_USER_ID = 1


def _resolve_user_id(user: User | None) -> int:
    """Resolve the effective user ID from the authenticated user.

    In auth-disabled mode (user is None), returns the default user ID (1).
    In auth-enabled mode, returns the authenticated user's ID.

    Args:
        user: The authenticated User object, or None if auth is disabled.

    Returns:
        The effective user ID for profile operations.
    """
    if user is None:
        return _DEFAULT_USER_ID
    return user.id


def _to_profile_read(profile: UserProfile) -> ProfileRead:
    """Convert a UserProfile database model to a ProfileRead response schema.

    Parses the JSON string in profile_data back to a dict for the API response.

    Args:
        profile: The UserProfile database object.

    Returns:
        ProfileRead schema suitable for API responses.
    """
    import json

    return ProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        profile_data=json.loads(profile.profile_data),
        is_default=profile.is_default,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=list[ProfileRead])
async def list_profiles(
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """List all profiles for the current user.

    In auth-disabled mode, returns profiles for the default user (ID 1).

    Args:
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        List of ProfileRead schemas.
    """
    user_id = _resolve_user_id(user)
    profiles = _service.list_profiles(user_id, session)
    return [_to_profile_read(p) for p in profiles]


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: ProfileCreate,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Create a new profile.

    If is_default is True, any existing default profile for this user is unset.

    Args:
        data: ProfileCreate schema with name, profile_data, is_default.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        ProfileRead schema for the newly created profile.
    """
    user_id = _resolve_user_id(user)
    profile = _service.create_profile(data, user_id, session)
    return _to_profile_read(profile)


@router.get("/default", response_model=ProfileRead)
async def get_default_profile(
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get the default profile for the current user.

    Args:
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        ProfileRead schema for the default profile.

    Raises:
        HTTPException: 404 if no default profile is set.
    """
    user_id = _resolve_user_id(user)
    profile = _service.get_default_profile(user_id, session)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default profile found",
        )
    return _to_profile_read(profile)


@router.post("/import", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
async def import_profile(
    data: ProfileCreate,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Import a profile from JSON data.

    Accepts a ProfileCreate body (same as create) — this endpoint exists
    for semantic clarity in the API (import vs. create).

    Args:
        data: ProfileCreate schema with name, profile_data, is_default.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        ProfileRead schema for the imported profile.
    """
    user_id = _resolve_user_id(user)
    profile = _service.create_profile(data, user_id, session)
    return _to_profile_read(profile)


@router.get("/{profile_id}", response_model=ProfileRead)
async def get_profile(
    profile_id: int,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Get a specific profile by ID (owner check enforced).

    Args:
        profile_id: The profile's database ID.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        ProfileRead schema for the requested profile.

    Raises:
        HTTPException: 404 if profile not found or not owned by user.
    """
    user_id = _resolve_user_id(user)
    profile = _service.get_profile(profile_id, user_id, session)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return _to_profile_read(profile)


@router.put("/{profile_id}", response_model=ProfileRead)
async def update_profile(
    profile_id: int,
    data: ProfileCreate,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Update a profile (owner check enforced).

    Args:
        profile_id: The profile's database ID.
        data: ProfileCreate schema with updated fields.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        ProfileRead schema for the updated profile.

    Raises:
        HTTPException: 404 if profile not found or not owned by user.
    """
    user_id = _resolve_user_id(user)
    profile = _service.update_profile(profile_id, user_id, data, session)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return _to_profile_read(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: int,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Delete a profile (owner check enforced).

    Args:
        profile_id: The profile's database ID.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException: 404 if profile not found or not owned by user.
    """
    user_id = _resolve_user_id(user)
    deleted = _service.delete_profile(profile_id, user_id, session)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return None


@router.get("/{profile_id}/export")
async def export_profile(
    profile_id: int,
    user: User | None = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Export a profile as a JSON dict.

    Args:
        profile_id: The profile's database ID.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Dict with full profile data ready for JSON serialization.

    Raises:
        HTTPException: 404 if profile not found or not owned by user.
    """
    user_id = _resolve_user_id(user)
    data = _service.export_profile(profile_id, user_id, session)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )
    return data

"""Profile management service for Fast-App.

This module provides CRUD operations for user profiles stored in the database.
Each user can have multiple profiles (e.g., "General", "Engineering Lead") with
one designated as the default. Profile data is stored as a JSON string matching
the profile.json file structure, enabling seamless import/export.

## Architecture

ProfileService follows the CLI-first pattern — all business logic lives here,
and both CLI commands and webapp routes delegate to these methods.

## JSON Storage

The `profile_data` column in UserProfile stores a JSON string (not a dict).
This module handles serialization (json.dumps) on create/update and
deserialization (json.loads) on read, so callers work with plain dicts.

## Auth-Disabled Mode

When auth is disabled, user_id defaults to 1. The service does not enforce
auth — that's the route layer's responsibility.

## Dependencies

This module requires the [auth] extra: pip install -e ".[auth]"
Imports sqlmodel lazily to allow graceful degradation.

See: docs/adr/003-sqlmodel-sqlite-auth.md, docs/guide/profiles.md
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlmodel import Session

from ..models.db_models import ProfileCreate, ProfilePatch, ProfileRead, UserProfile


class ProfileService:
    """CRUD service for user profiles.

    All methods that accept a user_id parameter verify profile ownership
    before performing operations. Profile data is serialized to/from JSON
    strings for database storage.

    Usage:
        service = ProfileService()
        profiles = service.list_profiles(user_id=1, session=session)
    """

    def list_profiles(self, user_id: int, session: Session) -> list[UserProfile]:
        """List all profiles for a user.

        Args:
            user_id: The owner's user ID.
            session: Database session.

        Returns:
            List of UserProfile objects belonging to the user.
        """
        from sqlmodel import select

        statement = select(UserProfile).where(UserProfile.user_id == user_id)
        return list(session.exec(statement).all())

    def get_profile(self, profile_id: int, user_id: int, session: Session) -> UserProfile | None:
        """Get a profile by ID with owner check.

        Args:
            profile_id: The profile's database ID.
            user_id: The owner's user ID (for security check).
            session: Database session.

        Returns:
            UserProfile if found and owned by user_id, None otherwise.
        """
        profile = session.get(UserProfile, profile_id)
        if profile is None or profile.user_id != user_id:
            return None
        return profile

    def create_profile(self, data: ProfileCreate, user_id: int, session: Session) -> UserProfile:
        """Create a new profile.

        If is_default is True, any existing default profile for this user
        is unset first (only one default per user).

        Args:
            data: ProfileCreate schema with name, profile_data, is_default.
            user_id: The owner's user ID.
            session: Database session.

        Returns:
            The newly created UserProfile.
        """
        if data.is_default:
            self._unset_default(user_id, session)

        profile = UserProfile(
            user_id=user_id,
            name=data.name,
            profile_data=json.dumps(data.profile_data),
            is_default=data.is_default,
        )
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile

    def update_profile(
        self, profile_id: int, user_id: int, data: ProfileCreate, session: Session
    ) -> UserProfile | None:
        """Update an existing profile (owner check enforced).

        Args:
            profile_id: The profile's database ID.
            user_id: The owner's user ID (for security check).
            data: ProfileCreate schema with updated fields.
            session: Database session.

        Returns:
            Updated UserProfile if found and owned, None otherwise.
        """
        profile = self.get_profile(profile_id, user_id, session)
        if profile is None:
            return None

        if data.is_default:
            self._unset_default(user_id, session)

        profile.name = data.name
        profile.profile_data = json.dumps(data.profile_data)
        profile.is_default = data.is_default
        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile

    def patch_profile(
        self, profile_id: int, user_id: int, data: ProfilePatch, session: Session
    ) -> UserProfile | None:
        """Partially update a profile with deep-merge of profile_data.

        Only fields present in the PatchData will be updated. For
        profile_data, the provided dict is deep-merged into the existing
        data, so nested keys can be updated independently without losing
        other nested fields.

        Args:
            profile_id: The profile's database ID.
            user_id: The owner's user ID (for security check).
            data: ProfilePatch schema with partial updates.
            session: Database session.

        Returns:
            Updated UserProfile if found and owned, None otherwise.
        """
        profile = self.get_profile(profile_id, user_id, session)
        if profile is None:
            return None

        if data.name is not None:
            profile.name = data.name

        if data.profile_data is not None:
            existing_data = json.loads(profile.profile_data)
            merged_data = self._deep_merge(existing_data, data.profile_data)
            profile.profile_data = json.dumps(merged_data)

        if data.is_default is not None:
            if data.is_default:
                self._unset_default(user_id, session)
            profile.is_default = data.is_default

        session.add(profile)
        session.commit()
        session.refresh(profile)
        return profile

    def delete_profile(self, profile_id: int, user_id: int, session: Session) -> bool:
        """Delete a profile (owner check enforced).

        Args:
            profile_id: The profile's database ID.
            user_id: The owner's user ID (for security check).
            session: Database session.

        Returns:
            True if deleted, False if not found or not owned by user.
        """
        profile = self.get_profile(profile_id, user_id, session)
        if profile is None:
            return False

        session.delete(profile)
        session.commit()
        return True

    def get_default_profile(self, user_id: int, session: Session) -> UserProfile | None:
        """Get the user's default profile.

        Args:
            user_id: The owner's user ID.
            session: Database session.

        Returns:
            The default UserProfile, or None if no default is set.
        """
        from sqlmodel import select

        statement = select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.is_default == True,  # noqa: E712
        )
        return session.exec(statement).first()

    def import_profile(
        self,
        file_path: str,
        user_id: int,
        session: Session,
        name: str = "Imported",
        is_default: bool = False,
    ) -> UserProfile:
        """Load a profile.json file and store it as a profile.

        Args:
            file_path: Path to the profile JSON file.
            user_id: The owner's user ID.
            session: Database session.
            name: Human-readable name for the imported profile.
            is_default: Whether to set this as the default profile.

        Returns:
            The newly created UserProfile.

        Raises:
            FileNotFoundError: If the file does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        path = Path(file_path)
        profile_data = json.loads(path.read_text(encoding="utf-8"))

        data = ProfileCreate(
            name=name,
            profile_data=profile_data,
            is_default=is_default,
        )
        return self.create_profile(data, user_id, session)

    def export_profile(self, profile_id: int, user_id: int, session: Session) -> dict | None:
        """Export a profile as a dict suitable for JSON output.

        Args:
            profile_id: The profile's database ID.
            user_id: The owner's user ID (for security check).
            session: Database session.

        Returns:
            Dict with profile data ready for JSON serialization,
            or None if profile not found or not owned by user.
        """
        profile = self.get_profile(profile_id, user_id, session)
        if profile is None:
            return None

        return ProfileRead(
            id=profile.id,
            user_id=profile.user_id,
            name=profile.name,
            profile_data=json.loads(profile.profile_data),
            is_default=profile.is_default,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        ).model_dump()

    def _unset_default(self, user_id: int, session: Session) -> None:
        """Unset the default flag on all profiles for a user.

        Args:
            user_id: The owner's user ID.
            session: Database session.
        """
        from sqlmodel import select

        statement = select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.is_default == True,  # noqa: E712
        )
        for profile in session.exec(statement).all():
            profile.is_default = False
            session.add(profile)
        session.commit()

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """Deep-merge override dict into base dict.

        For dict values, recursively merges. For all other values
        (including lists), the override replaces the base value.

        Args:
            base: The existing dict to merge into.
            override: The partial dict whose values take precedence.

        Returns:
            A new dict with merged values.
        """
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = ProfileService._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

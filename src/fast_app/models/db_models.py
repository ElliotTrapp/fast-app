"""Database models for user accounts and profiles.

This module defines SQLModel table models and Pydantic schemas for Fast-App's
authentication and profile management. SQLModel combines Pydantic validation
with SQLAlchemy ORM, so each model serves as both an API schema and a database
table definition.

## Table Models (database persistence)

- **User**: Email/password accounts with JWT authentication
- **UserProfile**: Per-user profile data stored as JSON

## Pydantic Schemas (API validation)

- **UserCreate**: Signup request (email + password)
- **UserRead**: User response (no password hash exposed)
- **TokenResponse**: JWT token response after login/signup
- **ProfileCreate**: Create/update profile request
- **ProfileRead**: Profile response with metadata

## Design Decisions

1. **profile_data as JSON string**: Stored as TEXT (JSON-encoded), not separate
   columns. This avoids schema migrations when profile format changes and matches
   the existing profile.json structure exactly.

2. **is_default flag**: Each user has one default profile. The CLI uses the
   default profile when no --profile-id is specified.

3. **No soft delete**: Users and profiles are hard-deleted. For a tool this
   simple, soft delete adds complexity without clear benefit.

4. **Hashed password stored directly**: No separate credential table. The
   hashed_password column on User uses bcrypt (see docs/adr/004-jwt-bcrypt-auth.md).

See: docs/adr/003-sqlmodel-sqlite-auth.md, docs/adr/004-jwt-bcrypt-auth.md
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """Database table for user accounts.

    Stores email, bcrypt-hashed password, and account status.
    Password is never stored in plaintext — only the bcrypt hash.

    Attributes:
        id: Auto-incrementing primary key
        email: Unique, indexed email address
        hashed_password: bcrypt hash of the user's password
        is_active: Whether the account is active (for soft deactivation)
        created_at: UTC timestamp of account creation
        updated_at: UTC timestamp of last update
    """

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class UserProfile(SQLModel, table=True):
    """Database table for user profiles.

    Each user can have multiple profiles (e.g., "General", "Engineering Lead").
    The profile_data column stores the same JSON structure as profile.json files,
    allowing seamless import/export between file-based and database storage.

    Attributes:
        id: Auto-incrementing primary key
        user_id: Foreign key to User table
        name: Human-readable profile name (e.g., "General", "Data Science")
        profile_data: JSON string containing the full profile (same shape as profile.json)
        is_default: Whether this is the user's default profile
        created_at: UTC timestamp of profile creation
        updated_at: UTC timestamp of last update
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(default="Default Profile")
    profile_data: str = Field(default="{}")  # JSON string
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class UserCreate(SQLModel):
    """Schema for signup request.

    Attributes:
        email: User's email address
        password: Plaintext password (will be hashed before storage)
    """

    email: str
    password: str


class UserRead(SQLModel):
    """Schema for user response (no password hash exposed).

    Attributes:
        id: User ID
        email: User's email address
        is_active: Whether the account is active
        created_at: When the account was created
    """

    id: int
    email: str
    is_active: bool
    created_at: datetime


class TokenResponse(SQLModel):
    """Schema for JWT token response after login/signup.

    Attributes:
        access_token: The JWT token string
        token_type: Always "bearer"
    """

    access_token: str
    token_type: str = "bearer"


class ProfileCreate(SQLModel):
    """Schema for creating or updating a profile.

    Attributes:
        name: Human-readable profile name
        profile_data: Profile data matching the profile.json structure
        is_default: Whether to set this as the default profile
    """

    name: str = "Default Profile"
    profile_data: dict
    is_default: bool = False


class ProfileRead(SQLModel):
    """Schema for profile response with metadata.

    Attributes:
        id: Profile ID
        user_id: Owner's user ID
        name: Profile name
        profile_data: The full profile data (parsed from JSON)
        is_default: Whether this is the default profile
        created_at: When the profile was created
        updated_at: When the profile was last updated
    """

    id: int
    user_id: int
    name: str
    profile_data: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ProfilePatch(SQLModel):
    """Schema for partial profile updates (PATCH).

    All fields are optional — only provided fields will be merged
    into the existing profile. profile_data is deep-merged with the
    existing data, so nested keys can be updated independently.

    Attributes:
        name: New profile name (optional)
        profile_data: Partial profile data to deep-merge (optional)
        is_default: Whether to set this as the default profile (optional)
    """

    name: str | None = None
    profile_data: dict | None = None
    is_default: bool | None = None

Task continued and completed in 4m 30s.

---

The user wants me to output the complete phased implementation plan I created earlier. They want the full detailed plan without summarization or truncation. I already have the complete plan from my previous response, so I'll output it in full.
# Fast-App Feature Implementation Plan

## Architecture Overview

**Current state**: Single-user CLI + webapp, JSON file caching, no auth, no database, no vector memory.

**Target state**: Multi-user auth, persistent profiles, ChromaDB vector memory, knowledge-informed question generation — all CLI-first, backward compatible.

---

## Phase 1: Multi-User Auth Foundation

**Goal**: Users can create accounts (email/password) on the webapp. CLI authenticates via API key/token. Existing single-user flow still works without auth (backward compatible).

**Complexity**: Medium | **Estimated effort**: 3-4 days

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/db.py` | SQLModel engine init, session factory, `get_session()` dependency, `init_db()` startup, DB path config (XDG-compliant) |
| `src/fast_app/models/db_models.py` | `User` SQLModel table: `id` (UUID), `email` (unique), `hashed_password`, `is_active`, `created_at`, `updated_at` |
| `src/fast_app/services/auth.py` | `hash_password()`, `verify_password()`, `create_access_token()`, `decode_access_token()`, `get_current_user()` dependency |
| `src/fast_app/webapp/auth_routes.py` | FastAPI router: `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/auth/me` |
| `tests/test_auth.py` | Unit tests for signup, login, token validation, password hashing |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add deps: `sqlmodel>=0.0.14`, `python-jose[cryptography]>=3.3`, `passlib[bcrypt]>=1.7`, `bcrypt>=4.0` |
| `src/fast_app/config.py` | Add `DatabaseConfig` dataclass (`path`, `jwt_secret`, `jwt_algorithm`, `jwt_expire_minutes`). Add `database: DatabaseConfig` field to `Config`. Load from config.json with defaults. Add env vars: `FAST_APP_DB_PATH`, `FAST_APP_JWT_SECRET` |
| `src/fast_app/webapp/app.py` | Import and include `auth_routes.router`. Add `init_db()` call in lifespan startup. Add `Depends(get_current_user)` to existing endpoints (optional/auth-gated via config flag) |
| `src/fast_app/__init__.py` | No changes needed (package init) |

### Key Design Decisions

1. **Backward compatibility**: When no `FAST_APP_JWT_SECRET` is set and no users exist in DB, auth is **disabled** — all endpoints work as today. Auth activates when first user signs up or env var is set.

2. **DB location**: `~/.fast-app/fast_app.db` (XDG-compliant, alongside existing `state.json`).

3. **CLI auth**: CLI gets `--token` flag. If provided, sent as `Authorization: Bearer <token>` header. If not provided and auth is enabled, CLI prompts for login and caches token in `~/.fast-app/auth.json`.

4. **SQLModel over SQLAlchemy**: Matches project's Pydantic-heavy style. SQLModel models are Pydantic models too — validation comes free.

### Auth Flow

```
Signup: POST /api/auth/signup {email, password} → {user_id, token}
Login:  POST /api/auth/login  {email, password} → {token, token_type: "bearer"}
Me:    GET  /api/auth/me      Authorization: Bearer <token> → {user}
```

### Detailed File Specifications

#### `src/fast_app/db.py`

```python
"""Database initialization and session management."""

import os
from pathlib import Path
from sqlmodel import SQLModel, Session, create_engine

_engine = None

def get_db_path() -> str:
    """Get database path from config or default."""
    db_path = os.environ.get("FAST_APP_DB_PATH")
    if db_path:
        return db_path
    state_dir = Path.home() / ".fast-app"
    state_dir.mkdir(parents=True, exist_ok=True)
    return str(state_dir / "fast_app.db")

def init_db(db_path: str | None = None) -> None:
    """Initialize database, creating tables if needed."""
    global _engine
    if db_path is None:
        db_path = get_db_path()
    db_url = f"sqlite:///{db_path}"
    _engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(_engine)

def get_session() -> Session:
    """Get a database session."""
    if _engine is None:
        init_db()
    return Session(_engine)

def get_engine():
    """Get the database engine."""
    if _engine is None:
        init_db()
    return _engine
```

#### `src/fast_app/models/db_models.py`

```python
"""SQLModel database models for multi-user support."""

import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from typing import Optional


class User(SQLModel, table=True):
    """User account for multi-user auth."""
    __tablename__ = "users"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCreate(SQLModel):
    """Schema for user signup."""
    email: str
    password: str


class UserLogin(SQLModel):
    """Schema for user login."""
    email: str
    password: str


class UserRead(SQLModel):
    """Schema for user response (no password)."""
    id: str
    email: str
    is_active: bool
    created_at: datetime


class Token(SQLModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"
```

#### `src/fast_app/services/auth.py`

```python
"""Authentication service: password hashing, JWT tokens, user dependency."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from ..models.db_models import User
from ..config import Config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    data: dict,
    secret_key: str,
    expires_delta: timedelta | None = None,
    algorithm: str = ALGORITHM,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=1440)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


def decode_access_token(token: str, secret_key: str, algorithm: str = ALGORITHM) -> dict | None:
    """Decode and validate a JWT access token. Returns None if invalid."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        return payload
    except JWTError:
        return None


def get_current_user(token: str, session: Session, secret_key: str) -> User | None:
    """Get the current user from a JWT token. Returns None if invalid."""
    payload = decode_access_token(token, secret_key)
    if payload is None:
        return None
    user_id: str | None = payload.get("sub")
    if user_id is None:
        return None
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def authenticate_user(email: str, password: str, session: Session) -> User | None:
    """Authenticate a user by email and password. Returns User if valid, None otherwise."""
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if user is None:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(email: str, password: str, session: Session) -> User:
    """Create a new user account."""
    hashed = hash_password(password)
    user = User(email=email, hashed_password=hashed)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
```

#### `src/fast_app/webapp/auth_routes.py`

```python
"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ..db import get_session
from ..models.db_models import User, UserCreate, UserLogin, UserRead, Token
from ..services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)
from ..config import load_config

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_secret_key() -> str:
    """Get JWT secret key from config."""
    config = load_config()
    return config.database.jwt_secret


@router.post("/signup", response_model=Token)
def signup(user_data: UserCreate, session: Session = Depends(get_session)):
    """Create a new user account."""
    # Check if user already exists
    existing = session.exec(
        select(User).where(User.email == user_data.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Validate password length
    if len(user_data.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    user = create_user(user_data.email, user_data.password, session)
    secret_key = _get_secret_key()
    access_token = create_access_token(data={"sub": user.id}, secret_key=secret_key)

    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
def login(user_data: UserLogin, session: Session = Depends(get_session)):
    """Authenticate and get a token."""
    user = authenticate_user(user_data.email, user_data.password, session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    secret_key = _get_secret_key()
    access_token = create_access_token(data={"sub": user.id}, secret_key=secret_key)

    return Token(access_token=access_token)


@router.get("/me", response_model=UserRead)
def get_me(token: str = None, session: Session = Depends(get_session)):
    """Get current user info."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    secret_key = _get_secret_key()
    user = get_current_user(token, session, secret_key)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    return UserRead(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
    )
```

### Config Changes — `src/fast_app/config.py`

Add to existing file:

```python
@dataclass
class DatabaseConfig:
    path: str = ""  # Empty = auto-detect (~/.fast-app/fast_app.db)
    jwt_secret: str = ""  # Empty = auto-generate on first run
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    resume: ReactiveResumeConfig = field(default_factory=ReactiveResumeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)  # NEW

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        # ... existing fields ...
        database_data = data.get("database", {})
        return cls(
            # ... existing fields ...
            database=DatabaseConfig(
                path=database_data.get("path", ""),
                jwt_secret=database_data.get("jwt_secret", ""),
                jwt_algorithm=database_data.get("jwt_algorithm", "HS256"),
                jwt_expire_minutes=database_data.get("jwt_expire_minutes", 1440),
            ),
        )
```

Add env var overrides in `from_file()`:

```python
if os.environ.get("FAST_APP_DB_PATH"):
    config.database.path = os.environ["FAST_APP_DB_PATH"]
if os.environ.get("FAST_APP_JWT_SECRET"):
    config.database.jwt_secret = os.environ["FAST_APP_JWT_SECRET"]
```

### Webapp Changes — `src/fast_app/webapp/app.py`

```python
# Add imports
from ..db import init_db
from .auth_routes import router as auth_router

# In lifespan():
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log_broadcaster.setup_logging()
    init_db()  # NEW: Initialize database

    if state_manager.is_active():
        state_manager.reset()

    yield

    # Shutdown
    if current_task and not current_task.done():
        current_task.cancel()

# Include auth router
app.include_router(auth_router)
```

### Test Strategy — Phase 1

- **Unit**: password hashing/verification, JWT creation/decoding, signup/login logic
- **Integration**: FastAPI TestClient hitting auth endpoints
- **Backward compat**: existing CLI commands work without DB/auth
- **Edge cases**: duplicate email signup, wrong password, expired token, inactive user

```python
# tests/test_auth.py structure
def test_hash_password():
    """Password hashing works and is verifiable."""

def test_verify_password_correct():
    """Correct password verifies successfully."""

def test_verify_password_incorrect():
    """Wrong password fails verification."""

def test_create_access_token():
    """JWT token creation and decoding works."""

def test_decode_expired_token():
    """Expired tokens are rejected."""

def test_signup_new_user(client, session):
    """New user signup succeeds."""

def test_signup_duplicate_email(client, session):
    """Duplicate email signup fails."""

def test_signup_short_password(client, session):
    """Short password is rejected."""

def test_login_valid(client, session):
    """Login with valid credentials returns token."""

def test_login_invalid_password(client, session):
    """Login with wrong password fails."""

def test_get_me_valid_token(client, session):
    """Get /me with valid token returns user info."""

def test_get_me_invalid_token(client, session):
    """Get /me with invalid token returns 401."""

def test_cli_without_auth():
    """CLI generate command works without auth enabled."""
```

---

## Phase 2: Persistent User Profiles

**Goal**: Users store profiles in SQLite. Profile CRUD via API and CLI. Existing `profile.json` becomes a migration/seed path.

**Complexity**: Medium | **Estimated effort**: 3-4 days | **Depends on**: Phase 1

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/services/profile_service.py` | `ProfileService` class: `create_profile()`, `get_profile()`, `update_profile()`, `delete_profile()`, `list_profiles()`, `import_from_json()`, `export_to_json()` |
| `src/fast_app/webapp/profile_routes.py` | FastAPI router: `GET /api/profiles`, `POST /api/profiles`, `GET /api/profiles/{id}`, `PUT /api/profiles/{id}`, `DELETE /api/profiles/{id}`, `POST /api/profiles/import` |
| `tests/test_profile_service.py` | CRUD tests, import/export tests, validation tests |

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/models/db_models.py` | Add `UserProfile` SQLModel table: `id` (UUID), `user_id` (FK→User), `name` (str), `profile_data` (JSON column), `is_default` (bool), `created_at`, `updated_at` |
| `src/fast_app/cli.py` | Add `profile` command group: `profile list`, `profile show`, `profile create`, `profile edit`, `profile import`, `profile export`. Modify `generate` to accept `--profile-id` for DB-backed profiles alongside existing `--profile` file path |
| `src/fast_app/utils/profile.py` | Add `load_profile_from_db(user_id, profile_id, session)` function. Modify `load_profile()` to try DB first, then file fallback |
| `src/fast_app/webapp/app.py` | Include `profile_routes.router` |
| `src/fast_app/webapp/background_tasks.py` | Accept `profile_id` parameter, load profile from DB if authenticated user |

### Key Design Decisions

1. **`profile_data` as JSON column**: Stores the same structure as current `profile.json` (basics, work, education, skills, etc.). This avoids schema migration when profile format changes.

2. **`is_default` flag**: Each user has one default profile. CLI `generate` uses default if no `--profile-id` specified.

3. **Migration path**: `profile import` reads existing `profile.json` and creates a DB record. `profile export` writes DB record to JSON file. Both directions supported.

4. **Backward compatibility**: If no DB/auth, `load_profile()` falls back to file-based loading exactly as today.

### Profile Schema (stored in `profile_data` JSON column)

```python
# Same as current profile.json structure:
{
    "basics": {"name": "...", "email": "...", ...},
    "work": [...],
    "education": [...],
    "skills": [...],
    "awards": [...],
    "certificates": [...],
    "projects": [...],
    "publications": [...],
    "preferences": {...},
    "narrative": {...}
}
```

### Detailed File Specifications

#### `src/fast_app/models/db_models.py` — Additions

```python
class UserProfile(SQLModel, table=True):
    """User profile stored in database."""
    __tablename__ = "user_profiles"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str = Field(default="Default Profile")
    profile_data: str = Field(default="{}")  # JSON string of profile data
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProfileCreate(SQLModel):
    """Schema for creating a profile."""
    name: str = "Default Profile"
    profile_data: dict  # Will be serialized to JSON string
    is_default: bool = False


class ProfileUpdate(SQLModel):
    """Schema for updating a profile."""
    name: str | None = None
    profile_data: dict | None = None
    is_default: bool | None = None


class ProfileRead(SQLModel):
    """Schema for profile response."""
    id: str
    user_id: str
    name: str
    profile_data: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime
```

#### `src/fast_app/services/profile_service.py`

```python
"""Profile service for CRUD operations on user profiles."""

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ..models.db_models import UserProfile


class ProfileService:
    """Service for managing user profiles in the database."""

    def __init__(self, session: Session):
        self.session = session

    def create_profile(
        self, user_id: str, name: str, profile_data: dict, is_default: bool = False
    ) -> UserProfile:
        """Create a new profile for a user."""
        # If setting as default, unset any existing default
        if is_default:
            self._unset_default(user_id)

        profile = UserProfile(
            user_id=user_id,
            name=name,
            profile_data=json.dumps(profile_data),
            is_default=is_default,
        )
        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def get_profile(self, profile_id: str) -> UserProfile | None:
        """Get a profile by ID."""
        return self.session.get(UserProfile, profile_id)

    def get_default_profile(self, user_id: str) -> UserProfile | None:
        """Get the default profile for a user."""
        statement = select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.is_default == True,  # noqa: E712
        )
        return self.session.exec(statement).first()

    def list_profiles(self, user_id: str) -> list[UserProfile]:
        """List all profiles for a user."""
        statement = select(UserProfile).where(UserProfile.user_id == user_id)
        return list(self.session.exec(statement))

    def update_profile(
        self,
        profile_id: str,
        name: str | None = None,
        profile_data: dict | None = None,
        is_default: bool | None = None,
    ) -> UserProfile | None:
        """Update a profile."""
        profile = self.session.get(UserProfile, profile_id)
        if profile is None:
            return None

        if name is not None:
            profile.name = name
        if profile_data is not None:
            profile.profile_data = json.dumps(profile_data)
        if is_default is not None:
            if is_default:
                self._unset_default(profile.user_id)
            profile.is_default = is_default

        self.session.add(profile)
        self.session.commit()
        self.session.refresh(profile)
        return profile

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile. Returns True if deleted."""
        profile = self.session.get(UserProfile, profile_id)
        if profile is None:
            return False
        self.session.delete(profile)
        self.session.commit()
        return True

    def import_from_json(
        self, user_id: str, file_path: str, name: str | None = None, is_default: bool = True
    ) -> UserProfile:
        """Import a profile from a JSON file."""
        path = Path(file_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Profile file not found: {path}")

        with open(path) as f:
            profile_data = json.load(f)

        profile_name = name or path.stem
        return self.create_profile(user_id, profile_name, profile_data, is_default)

    def export_to_json(self, profile_id: str, file_path: str) -> Path:
        """Export a profile to a JSON file."""
        profile = self.session.get(UserProfile, profile_id)
        if profile is None:
            raise ValueError(f"Profile not found: {profile_id}")

        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(json.loads(profile.profile_data), f, indent=2)

        return path

    def _unset_default(self, user_id: str) -> None:
        """Unset the default flag on all profiles for a user."""
        statement = select(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.is_default == True,  # noqa: E712
        )
        for profile in self.session.exec(statement):
            profile.is_default = False
            self.session.add(profile)
        self.session.commit()
```

#### `src/fast_app/webapp/profile_routes.py`

```python
"""Profile API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..models.db_models import ProfileCreate, ProfileRead, ProfileUpdate
from ..services.profile_service import ProfileService

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("/", response_model=list[ProfileRead])
def list_profiles(session: Session = Depends(get_session)):
    """List all profiles for the current user."""
    # TODO: Get user_id from auth context
    # For now, requires auth middleware to set user_id
    user_id = _get_current_user_id()
    service = ProfileService(session)
    profiles = service.list_profiles(user_id)
    return [
        ProfileRead(
            id=p.id,
            user_id=p.user_id,
            name=p.name,
            profile_data=json.loads(p.profile_data),
            is_default=p.is_default,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in profiles
    ]


@router.post("/", response_model=ProfileRead)
def create_profile(
    profile_data: ProfileCreate, session: Session = Depends(get_session)
):
    """Create a new profile."""
    user_id = _get_current_user_id()
    service = ProfileService(session)
    profile = service.create_profile(
        user_id=user_id,
        name=profile_data.name,
        profile_data=profile_data.profile_data,
        is_default=profile_data.is_default,
    )
    return ProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        profile_data=json.loads(profile.profile_data),
        is_default=profile.is_default,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: str, session: Session = Depends(get_session)):
    """Get a profile by ID."""
    service = ProfileService(session)
    profile = service.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        profile_data=json.loads(profile.profile_data),
        is_default=profile.is_default,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.put("/{profile_id}", response_model=ProfileRead)
def update_profile(
    profile_id: str, update: ProfileUpdate, session: Session = Depends(get_session)
):
    """Update a profile."""
    service = ProfileService(session)
    profile = service.update_profile(
        profile_id=profile_id,
        name=update.name,
        profile_data=update.profile_data,
        is_default=update.is_default,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        profile_data=json.loads(profile.profile_data),
        is_default=profile.is_default,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.delete("/{profile_id}")
def delete_profile(profile_id: str, session: Session = Depends(get_session)):
    """Delete a profile."""
    service = ProfileService(session)
    if not service.delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"status": "deleted"}


@router.post("/import", response_model=ProfileRead)
def import_profile(
    file_path: str, name: str | None = None, session: Session = Depends(get_session)
):
    """Import a profile from a JSON file."""
    user_id = _get_current_user_id()
    service = ProfileService(session)
    try:
        profile = service.import_from_json(user_id, file_path, name=name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ProfileRead(
        id=profile.id,
        user_id=profile.user_id,
        name=profile.name,
        profile_data=json.loads(profile.profile_data),
        is_default=profile.is_default,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _get_current_user_id() -> str:
    """Extract current user ID from auth context.

    This is a placeholder that will be replaced by actual auth dependency
    injection once Phase 1 auth is integrated.
    """
    # Will be: Depends(get_current_user) → user.id
    # For now, returns "default" for backward compatibility
    return "default"
```

### CLI Changes — `src/fast_app/cli.py`

Add profile command group:

```python
@main.group()
def profile():
    """Manage user profiles."""
    pass


@profile.command("list")
@click.option("--config", "-c", "config_path", default=None)
def list_profiles(config_path):
    """List all profiles."""
    from .db import init_db, get_session
    from .services.profile_service import ProfileService

    init_db()
    session = get_session()
    service = ProfileService(session)

    # TODO: Get user_id from auth context
    profiles = service.list_profiles("default")

    if not profiles:
        click.echo("No profiles found.")
        return

    click.echo(f"\n📋 Found {len(profiles)} profile(s):\n")
    for p in profiles:
        default_marker = " (default)" if p.is_default else ""
        click.echo(f"  {p.id[:8]}  {p.name}{default_marker}")
    click.echo()


@profile.command("show")
@click.argument("profile_id")
@click.option("--config", "-c", "config_path", default=None)
def show_profile(profile_id, config_path):
    """Show profile details."""
    import json
    from .db import init_db, get_session
    from .services.profile_service import ProfileService

    init_db()
    session = get_session()
    service = ProfileService(session)

    profile = service.get_profile(profile_id)
    if profile is None:
        raise click.ClickException(f"Profile not found: {profile_id}")

    click.echo(f"\n📋 Profile: {profile.name}")
    click.echo(f"   ID: {profile.id}")
    click.echo(f"   Default: {profile.is_default}")
    click.echo(f"   Created: {profile.created_at}")
    click.echo(f"\n{json.dumps(json.loads(profile.profile_data), indent=2)}")


@profile.command("import")
@click.argument("file_path")
@click.option("--name", "-n", default=None, help="Profile name (defaults to filename)")
@click.option("--default", "-d", "set_default", is_flag=True, help="Set as default profile")
@click.option("--config", "-c", "config_path", default=None)
def import_profile(file_path, name, set_default, config_path):
    """Import a profile from a JSON file."""
    from .db import init_db, get_session
    from .services.profile_service import ProfileService

    init_db()
    session = get_session()
    service = ProfileService(session)

    try:
        profile = service.import_from_json(
            "default", file_path, name=name, is_default=set_default
        )
        click.echo(f"✅ Imported profile: {profile.name} (ID: {profile.id[:8]})")
    except FileNotFoundError as e:
        raise click.ClickException(str(e))


@profile.command("export")
@click.argument("profile_id")
@click.argument("output_path")
@click.option("--config", "-c", "config_path", default=None)
def export_profile(profile_id, output_path, config_path):
    """Export a profile to a JSON file."""
    from .db import init_db, get_session
    from .services.profile_service import ProfileService

    init_db()
    session = get_session()
    service = ProfileService(session)

    try:
        path = service.export_to_json(profile_id, output_path)
        click.echo(f"✅ Exported profile to: {path}")
    except ValueError as e:
        raise click.ClickException(str(e))


@profile.command("delete")
@click.argument("profile_id")
@click.option("--config", "-c", "config_path", default=None)
def delete_profile(profile_id, config_path):
    """Delete a profile."""
    from .db import init_db, get_session
    from .services.profile_service import ProfileService

    init_db()
    session = get_session()
    service = ProfileService(session)

    if not service.delete_profile(profile_id):
        raise click.ClickException(f"Profile not found: {profile_id}")
    click.echo(f"✅ Deleted profile: {profile_id[:8]}")
```

Modify `generate` command to accept `--profile-id`:

```python
@main.command()
@click.option(
    "--profile-id",
    default=None,
    help="Database profile ID (overrides --profile file path)",
)
def generate(url, profile_path, profile_id, ...):
    """Generate and import resume for job URL."""
    # ... existing code ...

    # Profile loading: try DB first, then file
    if profile_id:
        from .db import init_db, get_session
        from .services.profile_service import ProfileService
        init_db()
        session = get_session()
        service = ProfileService(session)
        db_profile = service.get_profile(profile_id)
        if db_profile is None:
            raise click.ClickException(f"Profile not found: {profile_id}")
        profile = json.loads(db_profile.profile_data)
    else:
        profile = load_profile(profile_path)
```

### Utils Changes — `src/fast_app/utils/profile.py`

Add DB loading function:

```python
def load_profile_from_db(
    user_id: str, profile_id: str | None = None, session=None
) -> dict[str, Any] | None:
    """Load profile from database.

    Args:
        user_id: User ID
        profile_id: Profile ID (optional, uses default if not specified)
        session: SQLModel session

    Returns:
        Profile data dict or None if not found
    """
    if session is None:
        return None

    from ..services.profile_service import ProfileService

    service = ProfileService(session)

    if profile_id:
        profile = service.get_profile(profile_id)
    else:
        profile = service.get_default_profile(user_id)

    if profile is None:
        return None

    return json.loads(profile.profile_data)
```

### Test Strategy — Phase 2

- **Unit**: ProfileService CRUD operations
- **Integration**: API endpoints with auth
- **Migration**: import existing profile.json → DB, verify structure preserved
- **Backward compat**: `generate` works with file-based profile when no auth
- **Edge cases**: duplicate profile names, setting default unsets others, empty profile data

```python
# tests/test_profile_service.py structure
def test_create_profile(session):
    """Creating a profile stores it in DB."""

def test_create_default_profile_unsets_others(session):
    """Setting a profile as default unsets previous default."""

def test_get_profile(session):
    """Getting a profile by ID works."""

def test_get_default_profile(session):
    """Getting the default profile for a user works."""

def test_list_profiles(session):
    """Listing profiles for a user works."""

def test_update_profile(session):
    """Updating profile fields works."""

def test_delete_profile(session):
    """Deleting a profile removes it from DB."""

def test_import_from_json(session, tmp_path):
    """Importing a profile from JSON file works."""

def test_export_to_json(session, tmp_path):
    """Exporting a profile to JSON file works."""

def test_import_preserves_structure(session, tmp_path):
    """Imported profile preserves the exact structure of profile.json."""

def test_cli_profile_import(cli_runner, tmp_path):
    """CLI profile import command works."""

def test_cli_profile_list(cli_runner):
    """CLI profile list command works."""

def test_generate_with_file_profile(cli_runner):
    """Generate command works with file-based profile (backward compat)."""

def test_generate_with_db_profile(cli_runner):
    """Generate command works with DB-backed profile."""
```

---

## Phase 3: Vector Memory (Knowledge Extraction & Storage)

**Goal**: When a user answers questions, extract key facts, embed them in ChromaDB, and retrieve relevant knowledge in future sessions.

**Complexity**: High | **Estimated effort**: 5-6 days | **Depends on**: Phase 1, Phase 2

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/services/knowledge.py` | `KnowledgeService` class: `store_facts()`, `query_facts()`, `delete_facts()`, `list_facts()`. Wraps ChromaDB with per-user collections. Uses `OllamaEmbeddingFunction` with `nomic-embed-text` |
| `src/fast_app/services/fact_extractor.py` | `FactExtractor` class: `extract_facts_from_answers()`, `extract_facts_from_profile()`. Uses Ollama LLM to distill answers into discrete facts |
| `src/fast_app/prompts/fact_extraction.py` | Prompt template for fact extraction: given Q&A pairs and/or profile data, output structured facts with metadata (category, source, confidence) |
| `src/fast_app/models/knowledge.py` | Pydantic models: `ExtractedFact` (content, category, source, confidence), `FactExtractionResult` (facts list), `KnowledgeQuery` (query, user_id, n_results, filters) |
| `tests/test_knowledge.py` | ChromaDB integration tests: store, query, delete, per-user isolation |
| `tests/test_fact_extractor.py` | Fact extraction prompt tests, structured output validation |

### Modified Files

| File | Changes |
|------|---------|
| `pyproject.toml` | Add deps: `chromadb>=0.4.0` |
| `src/fast_app/config.py` | Add `ChromaConfig` dataclass (`path`, `collection_prefix`, `embedding_model`). Add `chroma: ChromaConfig` field to `Config`. Default: `path=~/.fast-app/chroma`, `embedding_model=nomic-embed-text` |
| `src/fast_app/cli.py` | Add `knowledge` command group: `knowledge list`, `knowledge search <query>`, `knowledge delete <id>`. Modify `generate` to auto-extract facts after Q&A and store in ChromaDB |
| `src/fast_app/services/ollama.py` | Add `extract_facts()` method that calls fact extraction prompt |
| `src/fast_app/webapp/app.py` | Include knowledge routes |
| `src/fast_app/webapp/background_tasks.py` | After answers collected, call `FactExtractor.extract_facts_from_answers()` → `KnowledgeService.store_facts()` |

### Key Design Decisions

1. **Per-user collections**: ChromaDB collection named `user_{user_id}_knowledge`. If no auth, use `default_knowledge`. This provides isolation without complex filtering.

2. **Fact structure**: Each fact stored with metadata:
   ```python
   {
       "content": "Has 5 years of Python experience",
       "category": "skill",       # skill, experience, preference, achievement, education
       "source": "qa_session",    # qa_session, profile_import, manual
       "confidence": 0.9,         # 0-1, from LLM
       "job_url": "...",          # original job URL (if from Q&A)
       "created_at": "2025-01-01T00:00:00Z"
   }
   ```

3. **Auto-extraction by default**: After Q&A, facts are automatically extracted and stored. `--review-facts` flag pauses for user review before storing.

4. **Embedding model**: `nomic-embed-text` via Ollama (already running locally). ChromaDB's `OllamaEmbeddingFunction` handles embedding calls.

5. **ChromaDB client**: `PersistentClient` for dev (local SQLite+Parquet), `HttpClient` for prod. Configurable via `chroma.client_type`.

### Detailed File Specifications

#### `src/fast_app/models/knowledge.py`

```python
"""Pydantic models for knowledge extraction and storage."""

from typing import Literal
from pydantic import BaseModel, Field


class ExtractedFact(BaseModel):
    """A single extracted fact about the candidate."""
    content: str = Field(
        ...,
        description="The fact content, e.g. 'Has 5 years of Python experience'",
    )
    category: Literal["skill", "experience", "preference", "achievement", "education"] = Field(
        ...,
        description="Category of the fact",
    )
    source: Literal["qa_session", "profile_import", "manual"] = Field(
        default="qa_session",
        description="Where this fact came from",
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score from LLM (0-1)",
    )


class FactExtractionResult(BaseModel):
    """Result of fact extraction from Q&A or profile data."""
    facts: list[ExtractedFact] = Field(
        default_factory=list,
        description="List of extracted facts",
    )


class KnowledgeQuery(BaseModel):
    """Query parameters for searching knowledge."""
    query: str = Field(..., description="Search query text")
    user_id: str = Field(default="default", description="User ID for collection isolation")
    n_results: int = Field(default=10, description="Number of results to return")
    category: str | None = Field(default=None, description="Filter by category")
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum confidence filter")


class KnowledgeSearchResult(BaseModel):
    """Result from a knowledge search."""
    id: str
    content: str
    category: str
    source: str
    confidence: float
    job_url: str | None
    created_at: str
    distance: float | None = None  # Similarity distance from ChromaDB
```

#### `src/fast_app/prompts/fact_extraction.py`

```python
"""Prompt templates for fact extraction from Q&A and profile data."""

import json
from typing import Any

from ..models.knowledge import FactExtractionResult


def get_fact_extraction_prompt(
    qa_pairs: list[dict[str, str]] | None = None,
    profile_summary: dict[str, Any] | None = None,
    job_context: dict[str, Any] | None = None,
) -> str:
    """Generate the prompt for extracting facts from Q&A and profile data.

    Args:
        qa_pairs: List of {question, answer} dicts
        profile_summary: User profile data dict
        job_context: Optional job data for context

    Returns:
        Prompt string for LLM
    """
    sections = []

    sections.append(
        """You are an expert at extracting discrete, atomic facts from candidate information.
Each fact should be:
- Atomic: one single piece of information
- Categorized: skill, experience, preference, achievement, or education
- Confidence-rated: how clearly stated (0.0 to 1.0)

## Categories
- **skill**: Technical or soft skills (e.g., "Proficient in Python", "Strong communication skills")
- **experience**: Work experience details (e.g., "Worked at Google for 3 years", "Led a team of 10")
- **preference**: Work style preferences (e.g., "Prefers remote work", "Values work-life balance")
- **achievement**: Quantifiable accomplishments (e.g., "Increased revenue by 30%", "Published 5 papers")
- **education**: Educational background (e.g., "MS in Computer Science from Stanford")"""
    )

    if qa_pairs:
        qa_text = "\n".join(
            f"Q: {pair['question']}\nA: {pair['answer']}" for pair in qa_pairs
        )
        sections.append(
            f"""## Q&A Session
{qa_text}"""
        )

    if profile_summary:
        sections.append(
            f"""## Candidate Profile Summary
{json.dumps(profile_summary, indent=2)}"""
        )

    if job_context:
        sections.append(
            f"""## Job Context (for relevance)
- Title: {job_context.get('title', 'Unknown')}
- Company: {job_context.get('company', 'Unknown')}
- Skills: {job_context.get('skills', 'Not specified')}"""
        )

    sections.append(
        f"""## Instructions
Extract ALL discrete facts from the above information. Each fact should be atomic
(one piece of information per fact). Rate confidence based on how explicitly
the information was stated (1.0 = directly stated, 0.5 = implied).

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{FactExtractionResult.model_json_schema()}

Return valid JSON matching the FactExtractionResult schema exactly."""
    )

    return "\n\n".join(sections)


def get_profile_fact_extraction_prompt(profile_data: dict[str, Any]) -> str:
    """Generate the prompt for extracting facts from profile data only.

    Args:
        profile_data: User profile data dict

    Returns:
        Prompt string for LLM
    """
    return f"""You are extracting key facts from a candidate's profile to build a knowledge base.
Each fact should be atomic, categorized, and confidence-rated.

## Candidate Profile
{json.dumps(profile_data, indent=2)}

## Categories
- **skill**: Technical or soft skills
- **experience**: Work experience details
- **preference**: Work style preferences
- **achievement**: Quantifiable accomplishments
- **education**: Educational background

## Instructions
Extract the most important facts from this profile. Focus on:
1. Technical skills and proficiency levels
2. Key work experiences and roles
3. Notable achievements with metrics
4. Educational background
5. Work preferences and values

Rate confidence as 1.0 for explicitly stated facts, 0.7 for implied facts.

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{FactExtractionResult.model_json_schema()}

Return valid JSON matching the FactExtractionResult schema exactly."""
```

#### `src/fast_app/services/fact_extractor.py`

```python
"""Fact extraction service using Ollama LLM."""

import asyncio
import json
from typing import Any

from ollama import Client

from ..models.knowledge import ExtractedFact, FactExtractionResult
from ..prompts.fact_extraction import (
    get_fact_extraction_prompt,
    get_profile_fact_extraction_prompt,
)
from ..log import logger


class FactExtractor:
    """Extract discrete facts from Q&A sessions and profile data using LLM."""

    def __init__(self, client: Client, model: str):
        self.client = client
        self.model = model

    def _strip_markdown_json(self, content: str) -> str:
        """Strip markdown code blocks from LLM response if present."""
        import re
        content = content.strip()
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    def extract_facts_from_answers(
        self,
        questions: list[str],
        answers: list[str],
        profile_data: dict[str, Any] | None = None,
        job_data: dict[str, Any] | None = None,
    ) -> list[ExtractedFact]:
        """Extract facts from Q&A pairs.

        Args:
            questions: List of questions asked
            answers: List of answers provided
            profile_data: Optional profile data for context
            job_data: Optional job data for context

        Returns:
            List of extracted facts
        """
        qa_pairs = [
            {"question": q, "answer": a}
            for q, a in zip(questions, answers)
            if a.strip()  # Skip empty answers
        ]

        if not qa_pairs:
            logger.warning("No non-empty Q&A pairs to extract facts from")
            return []

        prompt = get_fact_extraction_prompt(
            qa_pairs=qa_pairs,
            profile_summary=profile_data,
            job_context=job_data,
        )

        logger.header("Fact Extraction")
        logger.llm_call("extract_facts", {"qa_count": len(qa_pairs)})

        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=FactExtractionResult.model_json_schema(),
            think=False,
            options={"temperature": 0.1, "num_predict": 2000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = self._strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        try:
            extraction = FactExtractionResult.model_validate_json(cleaned)
            logger.llm_result("facts_extracted", {"count": len(extraction.facts)})
            return extraction.facts
        except Exception as e:
            logger.error(f"Failed to parse fact extraction result: {e}")
            logger.warning("Falling back to simple fact extraction")
            return self._simple_fact_extraction(qa_pairs)

    def extract_facts_from_profile(
        self,
        profile_data: dict[str, Any],
    ) -> list[ExtractedFact]:
        """Extract facts from profile data.

        Args:
            profile_data: User profile data dict

        Returns:
            List of extracted facts
        """
        prompt = get_profile_fact_extraction_prompt(profile_data)

        logger.header("Profile Fact Extraction")
        logger.llm_call("extract_profile_facts", {"profile_keys": list(profile_data.keys())})

        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=FactExtractionResult.model_json_schema(),
            think=False,
            options={"temperature": 0.1, "num_predict": 2000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = self._strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        try:
            extraction = FactExtractionResult.model_validate_json(cleaned)
            logger.llm_result("profile_facts_extracted", {"count": len(extraction.facts)})
            return extraction.facts
        except Exception as e:
            logger.error(f"Failed to parse profile fact extraction: {e}")
            return []

    def _simple_fact_extraction(
        self, qa_pairs: list[dict[str, str]]
    ) -> list[ExtractedFact]:
        """Fallback: create simple facts from Q&A pairs without LLM.

        Used when LLM extraction fails.
        """
        facts = []
        for pair in qa_pairs:
            facts.append(
                ExtractedFact(
                    content=f"Q: {pair['question']} A: {pair['answer']}",
                    category="experience",  # Default category
                    source="qa_session",
                    confidence=0.5,  # Lower confidence for fallback
                )
            )
        return facts
```

#### `src/fast_app/services/knowledge.py`

```python
"""Knowledge service: ChromaDB wrapper for storing and querying facts."""

import json
from datetime import datetime, timezone
from typing import Any

from chromadb import PersistentClient, HttpClient
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from ..models.knowledge import ExtractedFact, KnowledgeSearchResult
from ..log import logger


class KnowledgeService:
    """Manage knowledge storage and retrieval using ChromaDB."""

    def __init__(
        self,
        chroma_path: str = "~/.fast-app/chroma",
        embedding_model: str = "nomic-embed-text",
        ollama_host: str = "http://localhost:11434",
        client_type: str = "persistent",
    ):
        self.embedding_model = embedding_model
        self.ollama_host = ollama_host

        # Initialize embedding function
        self.embedding_function = OllamaEmbeddingFunction(
            url=ollama_host,
            model_name=embedding_model,
        )

        # Initialize ChromaDB client
        if client_type == "http":
            # For production: connect to running ChromaDB server
            self.client = HttpClient()
        else:
            # For development: persistent local storage
            from pathlib import Path
            db_path = Path(chroma_path).expanduser()
            db_path.mkdir(parents=True, exist_ok=True)
            self.client = PersistentClient(path=str(db_path))

    def _get_collection_name(self, user_id: str) -> str:
        """Get collection name for a user."""
        # ChromaDB collection names must be 3-63 chars, alphanumeric + _-
        sanitized = user_id.replace("-", "_")
        return f"user_{sanitized}_knowledge"

    def _get_or_create_collection(self, user_id: str):
        """Get or create a ChromaDB collection for a user."""
        collection_name = self._get_collection_name(user_id)
        return self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def store_facts(
        self,
        user_id: str,
        facts: list[ExtractedFact],
        job_url: str | None = None,
    ) -> list[str]:
        """Store extracted facts in ChromaDB.

        Args:
            user_id: User ID for collection isolation
            facts: List of extracted facts
            job_url: Optional job URL that generated these facts

        Returns:
            List of fact IDs
        """
        if not facts:
            logger.warning("No facts to store")
            return []

        collection = self._get_or_create_collection(user_id)

        ids = []
        documents = []
        metadatas = []

        for i, fact in enumerate(facts):
            import uuid
            fact_id = str(uuid.uuid4())
            ids.append(fact_id)
            documents.append(fact.content)

            metadata = {
                "category": fact.category,
                "source": fact.source,
                "confidence": str(fact.confidence),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if job_url:
                metadata["job_url"] = job_url

            metadatas.append(metadata)

        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        logger.cache_save("knowledge", f"{len(facts)} facts for user {user_id}")
        return ids

    def query_facts(
        self,
        user_id: str,
        query: str,
        n_results: int = 10,
        category: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[KnowledgeSearchResult]:
        """Query facts from ChromaDB using semantic search.

        Args:
            user_id: User ID for collection isolation
            query: Search query text
            n_results: Number of results to return
            category: Optional category filter
            min_confidence: Minimum confidence threshold

        Returns:
            List of knowledge search results
        """
        try:
            collection = self._get_or_create_collection(user_id)
        except Exception:
            logger.warning(f"No knowledge collection found for user {user_id}")
            return []

        # Build where filter
        where_filter = None
        if category:
            where_filter = {"category": category}

        results = collection.query(
            query_texts=[query],
            n_results=min(n_results, collection.count()) if collection.count() > 0 else 1,
            where=where_filter,
        )

        if not results or not results["ids"] or not results["ids"][0]:
            return []

        search_results = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if "distances" in results else None

            confidence = float(metadata.get("confidence", "0.5"))
            if confidence < min_confidence:
                continue

            search_results.append(
                KnowledgeSearchResult(
                    id=results["ids"][0][i],
                    content=doc,
                    category=metadata.get("category", "unknown"),
                    source=metadata.get("source", "unknown"),
                    confidence=confidence,
                    job_url=metadata.get("job_url"),
                    created_at=metadata.get("created_at", ""),
                    distance=distance,
                )
            )

        logger.cache_hit("knowledge", f"Found {len(search_results)} facts for query")
        return search_results

    def delete_facts(self, user_id: str, fact_ids: list[str]) -> None:
        """Delete specific facts from ChromaDB.

        Args:
            user_id: User ID for collection isolation
            fact_ids: List of fact IDs to delete
        """
        try:
            collection = self._get_or_create_collection(user_id)
            collection.delete(ids=fact_ids)
            logger.info(f"Deleted {len(fact_ids)} facts for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete facts: {e}")

    def list_facts(
        self,
        user_id: str,
        category: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeSearchResult]:
        """List all facts for a user, optionally filtered by category.

        Args:
            user_id: User ID for collection isolation
            category: Optional category filter
            limit: Maximum number of facts to return

        Returns:
            List of knowledge search results
        """
        try:
            collection = self._get_or_create_collection(user_id)
        except Exception:
            return []

        if collection.count() == 0:
            return []

        where_filter = None
        if category:
            where_filter = {"category": category}

        results = collection.get(
            limit=limit,
            where=where_filter,
        )

        if not results or not results["ids"]:
            return []

        facts = []
        for i, doc in enumerate(results["documents"]):
            metadata = results["metadatas"][i]
            facts.append(
                KnowledgeSearchResult(
                    id=results["ids"][i],
                    content=doc,
                    category=metadata.get("category", "unknown"),
                    source=metadata.get("source", "unknown"),
                    confidence=float(metadata.get("confidence", "0.5")),
                    job_url=metadata.get("job_url"),
                    created_at=metadata.get("created_at", ""),
                )
            )

        return facts

    def get_relevant_knowledge(
        self,
        user_id: str,
        job_data: dict[str, Any],
        n_results: int = 10,
    ) -> list[KnowledgeSearchResult]:
        """Get knowledge relevant to a specific job.

        Constructs a query from job data and searches for relevant facts.

        Args:
            user_id: User ID for collection isolation
            job_data: Job data dict with title, company, skills, etc.
            n_results: Number of results to return

        Returns:
            List of relevant knowledge search results
        """
        # Build query from job data
        query_parts = []
        if job_data.get("title"):
            query_parts.append(job_data["title"])
        if job_data.get("company"):
            query_parts.append(job_data["company"])
        if job_data.get("skills"):
            query_parts.append(job_data["skills"])
        if job_data.get("description"):
            # Use first 200 chars of description for query
            query_parts.append(job_data["description"][:200])

        query = " ".join(query_parts) if query_parts else "general experience"

        return self.query_facts(
            user_id=user_id,
            query=query,
            n_results=n_results,
        )
```

### Config Changes — `src/fast_app/config.py`

Add to existing file:

```python
@dataclass
class ChromaConfig:
    path: str = "~/.fast-app/chroma"
    embedding_model: str = "nomic-embed-text"
    client_type: str = "persistent"  # "persistent" or "http"
    host: str = "http://localhost:11434"  # Ollama host for embeddings


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    resume: ReactiveResumeConfig = field(default_factory=ReactiveResumeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)  # From Phase 1
    chroma: ChromaConfig = field(default_factory=ChromaConfig)  # NEW

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        # ... existing fields ...
        chroma_data = data.get("chroma", {})
        return cls(
            # ... existing fields ...
            chroma=ChromaConfig(
                path=chroma_data.get("path", "~/.fast-app/chroma"),
                embedding_model=chroma_data.get("embedding_model", "nomic-embed-text"),
                client_type=chroma_data.get("client_type", "persistent"),
                host=chroma_data.get("host", "http://localhost:11434"),
            ),
        )
```

Add env var overrides in `from_file()`:

```python
if os.environ.get("FAST_APP_CHROMA_PATH"):
    config.chroma.path = os.environ["FAST_APP_CHROMA_PATH"]
if os.environ.get("FAST_APP_CHROMA_MODEL"):
    config.chroma.embedding_model = os.environ["FAST_APP_CHROMA_MODEL"]
```

### CLI Changes — `src/fast_app/cli.py`

Add knowledge command group:

```python
@main.group()
def knowledge():
    """Manage knowledge base."""
    pass


@knowledge.command("list")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--limit", "-l", default=20, help="Maximum number of facts")
@click.option("--config", "-c", "config_path", default=None)
def list_knowledge(category, limit, config_path):
    """List stored facts."""
    from .db import init_db, get_session
    from .services.knowledge import KnowledgeService

    config = load_config(config_path)
    service = KnowledgeService(
        chroma_path=config.chroma.path,
        embedding_model=config.chroma.embedding_model,
        ollama_host=config.chroma.host,
    )

    # TODO: Get user_id from auth context
    facts = service.list_facts("default", category=category, limit=limit)

    if not facts:
        click.echo("No facts found in knowledge base.")
        return

    click.echo(f"\n🧠 Found {len(facts)} fact(s):\n")
    for fact in facts:
        click.echo(f"  [{fact.category}] {fact.content}")
        click.echo(f"    ID: {fact.id[:8]}  Confidence: {fact.confidence:.1f}  Source: {fact.source}")
    click.echo()


@knowledge.command("search")
@click.argument("query")
@click.option("--category", "-c", default=None, help="Filter by category")
@click.option("--limit", "-l", default=10, help="Maximum number of results")
@click.option("--config", "-c", "config_path", default=None)
def search_knowledge(query, category, limit, config_path):
    """Search knowledge base semantically."""
    from .services.knowledge import KnowledgeService

    config = load_config(config_path)
    service = KnowledgeService(
        chroma_path=config.chroma.path,
        embedding_model=config.chroma.embedding_model,
        ollama_host=config.chroma.host,
    )

    results = service.query_facts("default", query, n_results=limit, category=category)

    if not results:
        click.echo("No matching facts found.")
        return

    click.echo(f"\n🔍 Found {len(results)} matching fact(s):\n")
    for result in results:
        dist_str = f"  Distance: {result.distance:.3f}" if result.distance else ""
        click.echo(f"  [{result.category}] {result.content}")
        click.echo(f"    ID: {result.id[:8]}  Confidence: {result.confidence:.1f}{dist_str}")
    click.echo()


@knowledge.command("delete")
@click.argument("fact_id")
@click.option("--config", "-c", "config_path", default=None)
def delete_knowledge(fact_id, config_path):
    """Delete a fact from the knowledge base."""
    from .services.knowledge import KnowledgeService

    config = load_config(config_path)
    service = KnowledgeService(
        chroma_path=config.chroma.path,
        embedding_model=config.chroma.embedding_model,
        ollama_host=config.chroma.host,
    )

    service.delete_facts("default", [fact_id])
    click.echo(f"✅ Deleted fact: {fact_id[:8]}")
```

Modify `generate` command to extract and store facts:

```python
# In the generate() function, after answers are collected:

# After saving answers, extract and store facts
if answers and not skip_questions:
    try:
        from .services.knowledge import KnowledgeService
        from .services.fact_extractor import FactExtractor

        knowledge_service = KnowledgeService(
            chroma_path=config.chroma.path,
            embedding_model=config.chroma.embedding_model,
            ollama_host=config.chroma.host,
        )

        fact_extractor = FactExtractor(ollama.client, config.ollama.model)
        facts = fact_extractor.extract_facts_from_answers(
            questions=questions,
            answers=answers,
            profile_data=profile,
            job_data=job_data,
        )

        if facts:
            fact_ids = knowledge_service.store_facts(
                user_id="default",  # TODO: use actual user_id
                facts=facts,
                job_url=url,
            )
            logger.success(f"Stored {len(facts)} facts in knowledge base")
            if verbose and not debug:
                click.echo(f"   🧠 Stored {len(facts)} facts in knowledge base")
    except Exception as e:
        # Graceful degradation: if knowledge storage fails, continue
        logger.warning(f"Failed to store facts in knowledge base: {e}")
        if verbose:
            click.echo(f"   ⚠️  Knowledge storage failed: {e}")
```

### Background Tasks Changes — `src/fast_app/webapp/background_tasks.py`

Add fact extraction after answers are collected:

```python
# After saving answers (around line 128), add:

# Extract and store facts in knowledge base
try:
    from ..services.knowledge import KnowledgeService
    from ..services.fact_extractor import FactExtractor

    knowledge_service = KnowledgeService(
        chroma_path=config.chroma.path,
        embedding_model=config.chroma.embedding_model,
        ollama_host=config.chroma.host,
    )

    fact_extractor = FactExtractor(ollama.client, config.ollama.model)
    facts = await asyncio.to_thread(
        fact_extractor.extract_facts_from_answers,
        questions=questions,
        answers=answers,
        profile_data=profile,
        job_data=job_data,
    )

    if facts:
        fact_ids = knowledge_service.store_facts(
            user_id="default",  # TODO: use actual user_id
            facts=facts,
            job_url=url,
        )
        logger.success(f"Stored {len(facts)} facts in knowledge base")
except Exception as e:
    logger.warning(f"Knowledge storage failed (non-fatal): {e}")
```

### Test Strategy — Phase 3

- **Unit**: FactExtractor with mocked LLM responses
- **Integration**: KnowledgeService with ChromaDB PersistentClient (temp directory)
- **E2E**: Full flow — Q&A → fact extraction → storage → retrieval
- **Isolation**: Verify per-user collections don't leak data
- **Backward compat**: `generate` works without ChromaDB (graceful degradation)
- **Edge cases**: empty Q&A, ChromaDB unavailable, embedding model not running

```python
# tests/test_knowledge.py structure
def test_store_facts(knowledge_service):
    """Storing facts in ChromaDB works."""

def test_query_facts(knowledge_service):
    """Querying facts by semantic search works."""

def test_query_facts_with_category_filter(knowledge_service):
    """Category filtering works in queries."""

def test_delete_facts(knowledge_service):
    """Deleting facts from ChromaDB works."""

def test_list_facts(knowledge_service):
    """Listing all facts works."""

def test_per_user_isolation(knowledge_service):
    """Facts from one user are not visible to another."""

def test_empty_collection_query(knowledge_service):
    """Querying an empty collection returns empty results."""

def test_get_relevant_knowledge(knowledge_service):
    """Getting knowledge relevant to a job works."""

def test_fact_extractor_with_mocked_llm():
    """Fact extraction produces structured facts from Q&A."""

def test_fact_extractor_fallback():
    """Fallback fact extraction works when LLM fails."""

def test_profile_fact_extraction():
    """Extracting facts from profile data works."""

def test_graceful_degradation_without_chroma():
    """Generate command works when ChromaDB is unavailable."""
```

---

## Phase 4: Intelligent Question Generation

**Goal**: Questions are generated using relevant past knowledge. System avoids asking about known topics and fills knowledge gaps.

**Complexity**: Medium-High | **Estimated effort**: 4-5 days | **Depends on**: Phase 2, Phase 3

### New Files

| File | Purpose |
|------|---------|
| `src/fast_app/services/question_service.py` | `QuestionService` class: `generate_intelligent_questions()`. Orchestrates: (1) query ChromaDB for relevant knowledge, (2) analyze gaps between job requirements and known facts, (3) generate targeted questions |
| `src/fast_app/prompts/gap_analysis.py` | Prompt template for gap analysis: given job requirements + known facts, identify what information is missing |
| `src/fast_app/models/question.py` | Pydantic models: `KnowledgeContext` (facts, categories, gaps), `IntelligentQuestionResult` (questions with rationale) |
| `tests/test_question_service.py` | Gap analysis tests, question generation with knowledge context |

### Modified Files

| File | Changes |
|------|---------|
| `src/fast_app/prompts/questions.py` | Add `get_intelligent_questions_prompt()` that includes knowledge context and identified gaps. Keep existing `get_questions_prompt()` as fallback |
| `src/fast_app/services/ollama.py` | Add `generate_intelligent_questions()` method that uses knowledge context |
| `src/fast_app/cli.py` | Modify `generate` to use `QuestionService` when knowledge is available, fallback to standard questions otherwise |
| `src/fast_app/webapp/background_tasks.py` | Same: use `QuestionService` when knowledge available |

### Key Design Decisions

1. **Two-step process**: First, gap analysis (what do we know vs. what does the job need). Then, targeted question generation. This is more effective than one-shot "ask questions considering past knowledge."

2. **Knowledge injection**: Relevant facts are injected into the prompt as context, not as constraints. The LLM still generates natural questions but is informed about what's already known.

3. **Fallback**: If ChromaDB is empty or unavailable, falls back to standard question generation (current behavior). No degradation.

4. **Gap analysis categories**: Skills, experience, achievements, motivations, cultural fit, salary expectations. Each category is checked against known facts.

### Detailed File Specifications

#### `src/fast_app/models/question.py`

```python
"""Pydantic models for intelligent question generation."""

from typing import Literal
from pydantic import BaseModel, Field


class KnowledgeGap(BaseModel):
    """A gap in knowledge between job requirements and known facts."""
    category: Literal["skill", "experience", "achievement", "motivation", "cultural_fit"] = Field(
        ...,
        description="Category of the gap",
    )
    description: str = Field(
        ...,
        description="What information is missing",
    )
    priority: Literal["high", "medium", "low"] = Field(
        ...,
        description="Priority based on job importance",
    )
    job_requirement: str = Field(
        default="",
        description="The specific job requirement that creates this gap",
    )


class GapAnalysisResult(BaseModel):
    """Result of gap analysis between job requirements and known facts."""
    gaps: list[KnowledgeGap] = Field(
        default_factory=list,
        description="List of identified knowledge gaps",
    )


class KnowledgeContext(BaseModel):
    """Context from knowledge base for question generation."""
    relevant_facts: list[str] = Field(
        default_factory=list,
        description="Facts relevant to the current job",
    )
    fact_categories: list[str] = Field(
        default_factory=list,
        description="Categories of known facts",
    )
    identified_gaps: list[KnowledgeGap] = Field(
        default_factory=list,
        description="Gaps between job requirements and known facts",
    )


class IntelligentQuestionResult(BaseModel):
    """Result of intelligent question generation."""
    questions: list[str] = Field(
        default_factory=list,
        description="Generated questions",
    )
    rationale: list[str] = Field(
        default_factory=list,
        description="Why each question was generated (maps 1:1 with questions)",
    )
```

#### `src/fast_app/prompts/gap_analysis.py`

```python
"""Prompt template for gap analysis between job requirements and known facts."""

import json
from typing import Any

from ..models.question import GapAnalysisResult


def get_gap_analysis_prompt(
    job_data: dict[str, Any],
    known_facts: list[str],
    fact_categories: list[str] | None = None,
) -> str:
    """Generate the prompt for analyzing gaps between job requirements and known facts.

    Args:
        job_data: Extracted job data
        known_facts: List of known facts about the candidate
        fact_categories: Optional list of fact categories

    Returns:
        Prompt string for LLM
    """
    facts_text = "\n".join(f"- {fact}" for fact in known_facts) if known_facts else "No known facts."

    categories_text = ""
    if fact_categories:
        categories_text = f"\nKnown fact categories: {', '.join(set(fact_categories))}"

    return f"""You are analyzing a job posting against a candidate's known background.
Identify information gaps that would prevent writing an optimal resume and cover letter.

## Job Details
- Title: {job_data.get("title", "Unknown")}
- Company: {job_data.get("company", "Unknown")}
- Location: {job_data.get("location", "Unknown")}
- Description:
{job_data.get("description", "No description available")}

## Required Skills (from job)
{job_data.get("skills", "Not specified")}

## Known Candidate Facts
{facts_text}{categories_text}

## Categories to Check
For each category, determine if there are gaps between what the job requires
and what we already know about the candidate:

1. **skill**: Technical or soft skills mentioned in the job but not in candidate's known skills
2. **experience**: Relevant experience areas not covered by known facts
3. **achievement**: Quantifiable results that could strengthen the application
4. **motivation**: Why this role, why this company - personal motivation factors
5. **cultural_fit**: Work style preferences, team dynamics, company culture alignment

## Instructions
- Only identify gaps where information is TRULY missing (not where it can be inferred)
- Prioritize gaps that would most impact resume and cover letter quality
- Be specific about what information is needed
- Mark priority as "high" for gaps that directly match job requirements,
  "medium" for supporting information, "low" for nice-to-have details

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{GapAnalysisResult.model_json_schema()}

Return valid JSON matching the GapAnalysisResult schema exactly."""
```

#### `src/fast_app/services/question_service.py`

```python
"""Intelligent question generation service using knowledge base."""

import json
from typing import Any

from ollama import Client

from ..models.knowledge import KnowledgeSearchResult
from ..models.question import GapAnalysisResult, KnowledgeContext, KnowledgeGap
from ..prompts.gap_analysis import get_gap_analysis_prompt
from ..prompts.questions import get_intelligent_questions_prompt
from ..services.knowledge import KnowledgeService
from ..log import logger


class QuestionService:
    """Generate intelligent questions using knowledge base and gap analysis."""

    def __init__(
        self,
        client: Client,
        model: str,
        knowledge_service: KnowledgeService | None = None,
    ):
        self.client = client
        self.model = model
        self.knowledge_service = knowledge_service

    def _strip_markdown_json(self, content: str) -> str:
        """Strip markdown code blocks from LLM response if present."""
        import re
        content = content.strip()
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    def generate_intelligent_questions(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        user_id: str = "default",
    ) -> tuple[list[str], KnowledgeContext | None]:
        """Generate intelligent questions using knowledge base.

        This is a two-step process:
        1. Query knowledge base for relevant facts and analyze gaps
        2. Generate targeted questions that fill those gaps

        Args:
            job_data: Extracted job data
            profile_data: User profile data
            user_id: User ID for knowledge base isolation

        Returns:
            Tuple of (questions list, knowledge context used)
        """
        # Step 1: Get relevant knowledge
        relevant_facts: list[KnowledgeSearchResult] = []
        if self.knowledge_service:
            try:
                relevant_facts = self.knowledge_service.get_relevant_knowledge(
                    user_id=user_id,
                    job_data=job_data,
                    n_results=15,
                )
                logger.detail("relevant_facts_count", len(relevant_facts))
            except Exception as e:
                logger.warning(f"Knowledge query failed: {e}")
                relevant_facts = []

        # If no knowledge available, return None context (caller should use standard questions)
        if not relevant_facts:
            logger.info("No relevant knowledge found, using standard question generation")
            return [], None

        # Step 2: Analyze gaps
        facts_text = [f.content for f in relevant_facts]
        fact_categories = [f.category for f in relevant_facts]

        logger.header("Gap Analysis")
        logger.llm_call("gap_analysis", {
            "job_title": job_data.get("title", "Unknown"),
            "known_facts_count": len(facts_text),
        })

        gap_prompt = get_gap_analysis_prompt(job_data, facts_text, fact_categories)

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": gap_prompt}],
                format=GapAnalysisResult.model_json_schema(),
                think=False,
                options={"temperature": 0.1, "num_predict": 1000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)
            logger.llm_response(len(cleaned))

            gap_analysis = GapAnalysisResult.model_validate_json(cleaned)
            logger.llm_result("gaps_identified", {"count": len(gap_analysis.gaps)})

        except Exception as e:
            logger.error(f"Gap analysis failed: {e}")
            logger.warning("Falling back to standard question generation")
            return [], None

        # Step 3: Generate targeted questions
        knowledge_context = KnowledgeContext(
            relevant_facts=facts_text,
            fact_categories=fact_categories,
            identified_gaps=gap_analysis.gaps,
        )

        logger.header("Intelligent Question Generation")
        logger.llm_call("intelligent_questions", {
            "job_title": job_data.get("title", "Unknown"),
            "gaps_count": len(gap_analysis.gaps),
            "facts_count": len(facts_text),
        })

        question_prompt = get_intelligent_questions_prompt(
            job_data=job_data,
            profile_data=profile_data,
            known_facts=facts_text,
            gaps=gap_analysis.gaps,
        )

        from ..models import QuestionContent

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": question_prompt}],
                format=QuestionContent.model_json_schema(),
                think=False,
                options={"temperature": 0.3, "num_predict": 1000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)
            logger.llm_response(len(cleaned))

            question_data = QuestionContent.model_validate_json(cleaned)
            questions = question_data.questions[:8]

            logger.llm_result("intelligent_questions", {"count": len(questions)})
            for i, q in enumerate(questions, 1):
                logger.detail(f"Q{i}", q[:80] + "..." if len(q) > 80 else q)

            return questions, knowledge_context

        except Exception as e:
            logger.error(f"Intelligent question generation failed: {e}")
            logger.warning("Falling back to standard question generation")
            return [], None
```

### Prompt Changes — `src/fast_app/prompts/questions.py`

Add new function (keep existing `get_questions_prompt()` unchanged):

```python
def get_intelligent_questions_prompt(
    job_data: dict[str, Any],
    profile_data: dict[str, Any],
    known_facts: list[str],
    gaps: list,  # list of KnowledgeGap objects
) -> str:
    """Generate the prompt for intelligent question generation using knowledge context.

    Args:
        job_data: Extracted job data
        profile_data: User profile data
        known_facts: List of known facts about the candidate
        gaps: List of identified knowledge gaps

    Returns:
        Prompt string for LLM
    """
    facts_section = ""
    if known_facts:
        facts_text = "\n".join(f"- {fact}" for fact in known_facts)
        facts_section = f"""
## Known Candidate Information (from past sessions)
{facts_text}
"""

    gaps_section = ""
    if gaps:
        gaps_text = "\n".join(
            f"- [{g.priority.upper()}] {g.category}: {g.description}"
            for g in gaps
        )
        gaps_section = f"""
## Identified Knowledge Gaps
{gaps_text}
"""

    return f"""You are an expert career consultant preparing to write a compelling cover letter and tailored resume.

## Job Details
- Title: {job_data.get("title", "Unknown")}
- Company: {job_data.get("company", "Unknown")}
- Location: {job_data.get("location", "Unknown")}
- Description:
{job_data.get("description", "No description available")}

## Required Skills (from job)
{job_data.get("skills", "Not specified")}

## Candidate Profile Summary
{json.dumps(profile_data, indent=2)}
{facts_section}{gaps_section}
## Instructions
Based on the job requirements, candidate profile, known information, and identified gaps,
generate up to 8 questions to create the most compelling cover letter and tailored resume.

IMPORTANT RULES:
1. Do NOT ask about information already covered by the known facts
2. PRIORITIZE questions that fill the identified knowledge gaps (especially high-priority ones)
3. Focus on information that will most improve the cover letter and resume quality
4. Ask about:
   - Specific achievements relevant to this role
   - Why the candidate wants THIS company and THIS role
   - Details that differentiate the candidate from other applicants
   - Quantifiable results and metrics
5. Only ask questions where the answer would genuinely improve the application

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{QuestionContent.model_json_schema()}

Return valid JSON matching the QuestionContent schema exactly."""
```

### Ollama Service Changes — `src/fast_app/services/ollama.py`

Add method (keep existing `generate_questions()` unchanged):

```python
def generate_intelligent_questions(
    self,
    job_data: dict[str, any],
    profile_data: dict[str, any],
    knowledge_context: dict[str, any] | None = None,
) -> list[str]:
    """Generate intelligent questions using knowledge context.

    Falls back to standard question generation if no knowledge context.

    Args:
        job_data: Extracted job data
        profile_data: User profile data
        knowledge_context: Optional knowledge context from QuestionService

    Returns:
        List of question strings
    """
    # If no knowledge context, use standard generation
    if knowledge_context is None:
        return self.generate_questions(job_data, profile_data)

    # Use intelligent generation with knowledge context
    from ..prompts.questions import get_intelligent_questions_prompt

    known_facts = knowledge_context.get("relevant_facts", [])
    gaps = knowledge_context.get("identified_gaps", [])

    prompt = get_intelligent_questions_prompt(
        job_data=job_data,
        profile_data=profile_data,
        known_facts=known_facts,
        gaps=gaps,
    )

    # ... same LLM call pattern as generate_questions ...
    # (Uses same retry logic and structured output parsing)
```

### CLI Changes — `src/fast_app/cli.py`

Modify the question generation section in `generate()`:

```python
# Replace the standard question generation with intelligent generation
# when knowledge is available

# In the generate() function, where questions are generated:

if not skip_questions:
    questions_path = job_dir / "questions.json"
    answers_path = job_dir / "answers.json"

    if not force and questions_path.exists() and answers_path.exists():
        questions = cache.get_cached_questions(job_dir) or []
        answers = cache.get_cached_answers(job_dir) or []
        logger.cache_hit("questions", str(questions_path))
        logger.cache_hit("answers", str(answers_path))
        if verbose and not debug:
            logger.success("Using cached questions and answers")
    else:
        # Try intelligent question generation first
        questions = []
        try:
            from .services.knowledge import KnowledgeService
            from .services.question_service import QuestionService

            knowledge_service = KnowledgeService(
                chroma_path=config.chroma.path,
                embedding_model=config.chroma.embedding_model,
                ollama_host=config.chroma.host,
            )

            question_service = QuestionService(
                client=ollama.client,
                model=config.ollama.model,
                knowledge_service=knowledge_service,
            )

            intelligent_questions, context = question_service.generate_intelligent_questions(
                job_data=job_data,
                profile_data=profile,
                user_id="default",  # TODO: use actual user_id
            )

            if intelligent_questions:
                questions = intelligent_questions
                logger.success("Using intelligent questions from knowledge base")
                if verbose and not debug:
                    click.echo("   🧠 Using knowledge-informed questions")
        except Exception as e:
            logger.warning(f"Intelligent question generation failed: {e}")
            if verbose:
                click.echo(f"   ⚠️  Falling back to standard questions: {e}")

        # Fallback to standard question generation
        if not questions:
            questions = ollama.generate_questions(job_data, profile)

        if questions:
            cache.save_questions(job_dir, questions)
            # ... rest of existing code ...
```

### Background Tasks Changes — `src/fast_app/webapp/background_tasks.py`

Same pattern as CLI — try intelligent questions first, fallback to standard:

```python
# In the question generation section, replace:

# Try intelligent question generation first
questions = []
try:
    from ..services.knowledge import KnowledgeService
    from ..services.question_service import QuestionService

    knowledge_service = KnowledgeService(
        chroma_path=config.chroma.path,
        embedding_model=config.chroma.embedding_model,
        ollama_host=config.chroma.host,
    )

    question_service = QuestionService(
        client=ollama.client,
        model=config.ollama.model,
        knowledge_service=knowledge_service,
    )

    intelligent_questions, context = await asyncio.to_thread(
        question_service.generate_intelligent_questions,
        job_data=job_data,
        profile_data=profile,
        user_id="default",  # TODO: use actual user_id
    )

    if intelligent_questions:
        questions = intelligent_questions
        logger.success("Using intelligent questions from knowledge base")
except Exception as e:
    logger.warning(f"Intelligent question generation failed: {e}")

# Fallback to standard question generation
if not questions:
    questions = await asyncio.to_thread(
        ollama.generate_questions, job_data, profile
    )
```

### Test Strategy — Phase 4

- **Unit**: Gap analysis with mocked LLM, question generation with knowledge context
- **Integration**: Full flow — knowledge query → gap analysis → question generation
- **Regression**: Standard question generation still works when no knowledge available
- **Quality**: Verify generated questions don't overlap with known facts
- **Edge cases**: empty knowledge base, ChromaDB unavailable, LLM failure in gap analysis

```python
# tests/test_question_service.py structure
def test_gap_analysis_with_known_facts(mock_llm):
    """Gap analysis identifies gaps between job requirements and known facts."""

def test_gap_analysis_empty_knowledge(mock_llm):
    """Gap analysis with no known facts identifies all categories as gaps."""

def test_intelligent_question_generation(mock_llm, knowledge_service):
    """Intelligent questions are generated using knowledge context."""

def test_intelligent_questions_avoid_known_topics(mock_llm, knowledge_service):
    """Generated questions don't ask about topics already in knowledge base."""

def test_fallback_to_standard_questions():
    """Standard question generation is used when knowledge is unavailable."""

def test_fallback_on_gap_analysis_failure(mock_llm):
    """System falls back to standard questions when gap analysis fails."""

def test_fallback_on_knowledge_query_failure(mock_llm):
    """System falls back to standard questions when knowledge query fails."""

def test_full_flow_with_knowledge(mock_llm, knowledge_service):
    """Full flow: knowledge query → gap analysis → question generation."""

def test_regression_standard_questions_without_knowledge():
    """Existing question generation still works identically when no knowledge."""
```

---

## Phase Dependency Graph

```
Phase 1 (Auth) ──────────────────────┐
                                      ├── Phase 3 (Vector Memory)
Phase 2 (Profiles) ──────────────────┤
                                      ├── Phase 4 (Intelligent Questions)
                                      │
                    Phase 3 ──────────→ Phase 4
```

- **Phase 1** and **Phase 2** can be developed in parallel (both depend only on current codebase)
- **Phase 3** depends on Phase 1 (user isolation in ChromaDB) and Phase 2 (profile data for fact extraction)
- **Phase 4** depends on Phase 2 (profiles) and Phase 3 (knowledge retrieval)

---

## Cross-Cutting Concerns

### Database Migration Strategy

```python
# src/fast_app/db.py
from sqlmodel import SQLModel, create_engine, Session

def init_db(db_path: str | None = None):
    """Initialize database, creating tables if needed.
    
    Uses SQLModel's create_all() which is safe for initial schema creation.
    For future schema changes, add Alembic migrations.
    """
    if db_path is None:
        db_path = get_db_path()
    
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url, echo=False, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine
```

No migration tool needed initially — SQLModel's `create_all()` handles initial schema. For future schema changes, add Alembic in a later phase.

### Configuration Changes

```json
{
    "ollama": {
        "endpoint": "http://localhost:11434",
        "model": "llama3.2",
        "cloud": false,
        "debug": false,
        "api_key": ""
    },
    "resume": {
        "endpoint": "http://localhost:3000",
        "api_key": ""
    },
    "output": {
        "directory": "generated"
    },
    "database": {
        "path": "~/.fast-app/fast_app.db",
        "jwt_secret": "",
        "jwt_algorithm": "HS256",
        "jwt_expire_minutes": 1440
    },
    "chroma": {
        "path": "~/.fast-app/chroma",
        "embedding_model": "nomic-embed-text",
        "client_type": "persistent",
        "host": "http://localhost:11434"
    }
}
```

### Backward Compatibility Rules

1. **No auth required by default**: If `jwt_secret` is empty and no users exist, all endpoints work without auth
2. **File-based profiles still work**: `--profile` flag continues to accept file paths
3. **ChromaDB is optional**: If ChromaDB is not configured or unavailable, system falls back to standard question generation
4. **Existing cache system preserved**: `CacheManager` continues to work alongside DB storage
5. **All existing tests pass**: No changes to existing test files unless adding new test cases
6. **Existing CLI commands unchanged**: `generate`, `test-connection`, `list`, `status`, `serve` all work identically

### Error Handling Pattern

Following existing patterns from `ollama.py` and `reactive_resume.py`:
- Retry with exponential backoff for ChromaDB operations
- Graceful degradation: if knowledge service fails, log warning and continue without it
- Structured error messages with suggestions (matching existing style)
- All new services follow the same `with_retry` decorator pattern

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| ChromaDB embedding model not available | Questions fall back to standard generation | Check `nomic-embed-text` availability at startup, warn if missing |
| SQLite concurrency under webapp | Data corruption | Use `check_same_thread=False` with connection pooling; SQLite handles read concurrency well |
| JWT secret management | Security vulnerability | Auto-generate if not set; warn in logs; support env var override |
| Profile JSON schema evolution | Migration complexity | Store as JSON column, validate on read, not on write |
| Large knowledge base slows queries | Poor UX | Limit query results, add category filtering, periodic cleanup |
| Ollama model not running for embeddings | Knowledge service unavailable | Pre-check connection, graceful fallback |
| ChromaDB version incompatibility | Installation failures | Pin chromadb version in pyproject.toml, test with specific version |
| Fact extraction produces low-quality facts | Noisy knowledge base | Confidence filtering, `--review-facts` flag for manual review |
| Gap analysis hallucinates gaps | Irrelevant questions | LLM temperature=0.1 for gap analysis, validate gaps against actual job requirements |

---

## Implementation Order Within Each Phase

### Phase 1 Order
1. Add dependencies to `pyproject.toml`
2. Create `db.py` (engine, session, init)
3. Create `models/db_models.py` (User model)
4. Create `services/auth.py` (password + JWT)
5. Create `webapp/auth_routes.py` (signup/login/me)
6. Modify `config.py` (add DB + auth config)
7. Modify `webapp/app.py` (include auth routes, init_db)
8. Write tests
9. Verify backward compatibility

### Phase 2 Order
1. Add `UserProfile` model to `models/db_models.py`
2. Create `services/profile_service.py`
3. Create `webapp/profile_routes.py`
4. Modify `utils/profile.py` (add DB loading)
5. Add CLI `profile` commands to `cli.py`
6. Modify `webapp/background_tasks.py` (accept profile_id)
7. Write tests
8. Test import/export flow with existing `profile.json`

### Phase 3 Order
1. Add `chromadb` dependency to `pyproject.toml`
2. Add `ChromaConfig` to `config.py`
3. Create `models/knowledge.py` (Pydantic models)
4. Create `prompts/fact_extraction.py`
5. Create `services/fact_extractor.py`
6. Create `services/knowledge.py` (ChromaDB wrapper)
7. Modify `cli.py` (add knowledge commands, integrate into generate)
8. Modify `webapp/background_tasks.py` (integrate fact extraction)
9. Write tests
10. Test full flow: Q&A → extraction → storage → retrieval

### Phase 4 Order
1. Create `models/question.py` (gap analysis models)
2. Create `prompts/gap_analysis.py`
3. Create `services/question_service.py`
4. Modify `prompts/questions.py` (add intelligent prompt)
5. Modify `services/ollama.py` (add intelligent question method)
6. Modify `cli.py` (use QuestionService in generate)
7. Modify `webapp/background_tasks.py` (use QuestionService)
8. Write tests
9. Test regression: standard questions still work without knowledge

---

## Summary

| Phase | Effort | New Files | Modified Files | Key Dependency |
|-------|--------|-----------|----------------|----------------|
| 1. Auth | 3-4 days | 5 | 4 | None |
| 2. Profiles | 3-4 days | 3 | 5 | Phase 1 |
| 3. Vector Memory | 5-6 days | 6 | 5 | Phase 1, 2 |
| 4. Intelligent Questions | 4-5 days | 4 | 4 | Phase 2, 3 |
| **Total** | **15-19 days** | **18** | **18** | |

Each phase is independently deployable and backward compatible. Phases 1 and 2 can be parallelized. Phase 3 requires both. Phase 4 requires 2 and 3.

<task_metadata>
session_id: ses_24a19c652ffeFlrhBnAB25Tnqc
subagent: Sisyphus-Junior
</task_metadata>
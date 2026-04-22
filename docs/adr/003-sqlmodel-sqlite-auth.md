# ADR-003: SQLModel + SQLite for Auth and Profiles

## Context

Fast-App currently has no database layer. User data lives in `profile.json` files, job data in flat JSON caches under `output/<company>/<title>/`, and there's no concept of user accounts or authentication.

We need to add:
1. **User accounts** — email, hashed password, creation date
2. **User profiles** — stored per-user, queryable, importable from existing JSON
3. **Session management** — JWT tokens referencing user IDs

### Why a database now?

Without a database, multi-user support is impossible. JSON files cannot be queried, have no referential integrity, and cannot enforce uniqueness constraints (duplicate emails, etc.). The webapp needs to know _who_ is making each request.

### Why SQLModel?

[SQLModel](https://sqlmodel.tiangolo.com/) is authored by Sebastián Ramírez, the same author as FastAPI. It's a Pydantic + SQLAlchemy hybrid:

- Write a class once, it's both a **Pydantic model** (for API validation) and a **SQLAlchemy table** (for DB persistence)
- No duplicate schemas — no ORM schema vs. API schema mismatch
- Type-annotated, editor-friendly, validation built-in
- Async support via `aiosqlite` for SQLite, asyncpg for PostgreSQL
- Same patterns FastAPI developers already know

### Alternatives considered

| Approach | Pros | Cons |
|----------|------|------|
| **SQLModel + SQLite** | Same author as FastAPI, models = schemas + tables, zero infra for dev, PostgreSQL migration path | SQLModel is relatively young (pre-1.0), less community examples |
| **SQLAlchemy + Alembic** | Battle-tested, huge ecosystem, mature | Double schemas (ORM model + Pydantic model), more boilerplate |
| **Tortoise ORM** | Async-native, Django-like API | Different paradigm than FastAPI, less adopted |
| **Pure Pydantic + JSON** | No new dependency | No queries, no relationships, no ACID, no multi-user |
| **MongoDB + Beanie** | Document model fits profile data well | New infra dependency, overkill for auth/user tables |

## Decision

Use **SQLModel** with **SQLite** (`aiosqlite` for async) for development. The connection string is configured, so production can switch to PostgreSQL by changing one environment variable.

### Database schema

```python
# models/db_models.py

class User(SQLModel, table=True):
    """Database table for user accounts."""
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserProfile(SQLModel, table=True):
    """Database table for user profiles."""
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str = Field(default="Default Profile")
    profile_data: str  # JSON string — same shape as profile.json
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### Pydantic schemas (API input/output)

Separate from the table models, we define Pydantic-only schemas for API validation:

```python
class UserCreate(SQLModel):
    """Schema for signup request."""
    email: str
    password: str


class UserRead(SQLModel):
    """Schema for user response (no password hash)."""
    id: int
    email: str
    is_active: bool
    created_at: datetime


class TokenResponse(SQLModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class ProfileCreate(SQLModel):
    """Schema for creating/updating a profile."""
    name: str = "Default Profile"
    profile_data: dict  # Same shape as profile.json
    is_default: bool = False


class ProfileRead(SQLModel):
    """Schema for profile response."""
    id: int
    user_id: int
    name: str
    profile_data: dict
    is_default: bool
    created_at: datetime
    updated_at: datetime
```

### Database functions

```python
# db.py

from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

sync_engine = create_engine("sqlite:///~/.fast-app/fast_app.db")
async_engine = create_async_engine("sqlite+aiosqlite:///~/.fast-app/fast_app.db")

def init_db():
    """Create all tables if they don't exist."""
    SQLModel.metadata.create_all(sync_engine)

def get_session() -> Generator[Session, None, None]:
    """Dependency for FastAPI — yields a DB session."""
    with Session(sync_engine) as session:
        yield session
```

### Backward compatibility

When `FAST_APP_JWT_SECRET` is not set and no users exist in the database:
- Auth is **disabled** — all endpoints work as they do today
- No login required, no tokens checked
- `Depends(get_current_user)` returns `None` or a sentinel "anonymous" user
- This ensures the CLI keeps working without any auth setup

When `FAST_APP_JWT_SECRET` is set OR users exist in the database:
- Auth is **enabled** — protected endpoints require a valid Bearer token
- CLI supports `--token` flag for authentication
- Webapp shows login/signup forms

### Migration path

SQLite → PostgreSQL is a connection string change:

```bash
# Development (default)
FAST_APP_DB_PATH=""  # Uses ~/.fast-app/fast_app.db

# Production
FAST_APP_DB_PATH="postgresql+asyncpg://user:pass@localhost/fast_app"
```

SQLModel handles both transparently. The only code change is the engine creation string.

## Consequences

### Positive

- **Zero infra for dev**: SQLite creates a file. No server, no Docker, no setup.
- **Pydantic everywhere**: Table models double as API schemas. No duplication.
- **FastAPI-native**: `get_session()` as a dependency, `Depends(get_current_user)` for auth — idiomatic FastAPI patterns.
- **PostgreSQL ready**: Connection string swap for production. SQLModel handles dialect differences.
- **Profile flexibility**: `profile_data` is a JSON column, so schema changes in profile structure don't require DB migrations.

### Negative

- **SQLModel maturity**: Pre-1.0, occasional rough edges. Mitigated by: simple schema, no complex queries, well-documented patterns.
- **No Alembic yet**: We'll use `SQLModel.metadata.create_all()` for table creation. Migration support (Alembic) can be added later when schema changes require it.
- **JSON column**: `profile_data` as a JSON string means we can't query individual fields with SQL. This is intentional — profiles are loaded wholesale, never queried by field.
- **No async in CLI**: The CLI uses sync `Session`. The webapp uses sync sessions too (simpler), with async available for future WebSocket improvements.
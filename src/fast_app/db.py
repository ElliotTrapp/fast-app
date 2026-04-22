"""Database initialization and session management.

This module provides SQLModel/SQLAlchemy database engine setup, session management,
and table initialization for Fast-App's SQLite database.

## Architecture

The database layer uses SQLModel (Pydantic + SQLAlchemy hybrid) with SQLite for
development and supports PostgreSQL for production via connection string change.

## Usage

    from fast_app.db import init_db, get_session

    # Initialize database (create tables if needed)
    init_db()

    # Get a database session (for FastAPI dependency injection)
    with next(get_session()) as session:
        user = session.get(User, 1)

## Configuration

Database path is configured via:
1. `config.database.path` in config.json
2. `FAST_APP_DB_PATH` environment variable
3. Default: `~/.fast-app/fast_app.db`

## Thread Safety

SQLite with sync sessions is used for simplicity. The webapp creates one session
per request via `Depends(get_session)`. For future async needs, switch to
`create_async_engine` with `aiosqlite`.

See: docs/adr/003-sqlmodel-sqlite-auth.md
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import Config


def _get_db_path(config: Config | None = None) -> str:
    """Determine the database file path.

    Priority:
    1. config.database.path (if set and non-empty)
    2. FAST_APP_DB_PATH environment variable
    3. Default: ~/.fast-app/fast_app.db

    Args:
        config: Application config. If None, uses environment defaults.

    Returns:
        SQLite connection string (sqlite:///path/to/db).
    """
    if config and config.database.path:
        db_path = config.database.path
    else:
        env_path = os.environ.get("FAST_APP_DB_PATH")
        if env_path:
            db_path = env_path
        else:
            xdg_data = os.environ.get("XDG_DATA_HOME", "~/.local/share")
            db_dir = Path(xdg_data).expanduser() / "fast-app"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "fast_app.db")

    return f"sqlite:///{db_path}"


_engine = None


def get_engine(config: Config | None = None):
    """Get or create the database engine.

    Args:
        config: Application config for database path. If None, uses defaults.

    Returns:
        SQLModel/SQLAlchemy engine instance.
    """
    global _engine
    if _engine is None:
        db_url = _get_db_path(config)
        _engine = create_engine(db_url, echo=False)
    return _engine


def init_db(config: Config | None = None) -> None:
    """Initialize the database, creating all tables if they don't exist.

    This is called once at application startup (CLI or webapp lifespan).
    It creates the User, UserProfile, and all other SQLModel tables.

    Args:
        config: Application config for database path. If None, uses defaults.
    """
    from .models.db_models import User, UserProfile  # noqa: F401

    engine = get_engine(config)
    SQLModel.metadata.create_all(engine)


def get_session(config: Config | None = None) -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session.

    Usage in FastAPI routes:
        @router.get("/me")
        async def get_me(user: User = Depends(get_current_user),
                         session: Session = Depends(get_session)):
            ...

    Args:
        config: Application config for database path. If None, uses defaults.

    Yields:
        SQLModel Session connected to the database.
    """
    engine = get_engine(config)
    with Session(engine) as session:
        yield session


def reset_engine() -> None:
    """Reset the module-level engine. Useful for testing."""
    global _engine
    _engine = None
"""Shared FastAPI dependencies for the webapp.

Provides common dependency resolution functions used across
multiple route modules, eliminating the _resolve_user_id
duplication that existed in 4 separate route files.
"""

from __future__ import annotations

from ..models.db_models import User

# Fallback user ID when auth is disabled
DEFAULT_USER_ID = 1


def resolve_user_id(user: User | None) -> int:
    """Resolve the effective user ID from the authenticated user.

    In auth-disabled mode (user is None), returns the default user ID (1).
    In auth-enabled mode, returns the authenticated user's ID.

    Args:
        user: The authenticated User object, or None if auth is disabled.

    Returns:
        The effective user ID for per-user operations.
    """
    if user is None:
        return DEFAULT_USER_ID
    return user.id

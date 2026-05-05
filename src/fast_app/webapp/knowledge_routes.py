"""FastAPI knowledge routes for searching and managing learned facts.

This module defines the REST API endpoints for Fast-App's knowledge system.
All routes are mounted under `/api/knowledge/` and follow the CLI-first architecture:
route handlers are thin wrappers that delegate to KnowledgeService.

## Endpoints

- GET  /api/knowledge/search  — Semantic search across user's knowledge base
- GET  /api/knowledge/facts    — List facts with optional category filter
- DELETE /api/knowledge/facts  — Delete facts by IDs

## Auth-Disabled Mode

When FAST_APP_JWT_SECRET is not set and no users exist in the database,
authentication is disabled. In this mode, user_id defaults to 1 for all
operations, providing backward compatibility for single-user setups.

## Graceful Degradation

If ChromaDB is not installed (missing [knowledge] dependency group), all
endpoints return empty results. The system works identically to how it does
without knowledge features.

See: docs/adr/002-chromadb-vector-memory.md, docs/guide/knowledge.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..config import load_config
from ..db import SessionDep
from ..models.db_models import User
from ..models.knowledge import KnowledgeSearchResult
from ..services.auth import get_current_user
from ..services.knowledge import KnowledgeService

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# Fallback user ID when auth is disabled
_DEFAULT_USER_ID = 1


def _resolve_user_id(user: User | None) -> int:
    """Resolve the effective user ID from the authenticated user.

    In auth-disabled mode (user is None), returns the default user ID (1).
    In auth-enabled mode, returns the authenticated user's ID.

    Args:
        user: The authenticated User object, or None if auth is disabled.

    Returns:
        The effective user ID for knowledge operations.
    """
    if user is None:
        return _DEFAULT_USER_ID
    return user.id


def _get_service(user_id: int) -> KnowledgeService:
    """Create a KnowledgeService instance for the given user.

    Args:
        user_id: The user ID for per-user collection isolation.

    Returns:
        KnowledgeService configured with the app config and user ID.
    """
    config = load_config()
    return KnowledgeService(config, user_id)


class DeleteFactsRequest(BaseModel):
    """Request body for deleting facts by ID."""

    ids: list[str] = Field(..., min_length=1, description="List of fact IDs to delete")


@router.get("/search", response_model=list[KnowledgeSearchResult])
async def search_facts(
    query: str,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
    n: int = 5,
    category: str | None = None,
):
    """Search for facts semantically related to a query.

    Args:
        query: Natural language search string (required).
        n: Number of results to return (default 5, max 50).
        category: Optional category filter (e.g., "skill", "experience").
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        List of KnowledgeSearchResult objects ranked by relevance.
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    results = service.query_facts(query=query, n=n, category=category)
    return results


@router.get("/facts", response_model=list[KnowledgeSearchResult])
async def list_facts(
    session: SessionDep,
    user: User | None = Depends(get_current_user),
    limit: int = 100,
    category: str | None = None,
):
    """List all facts in the user's knowledge collection.

    Args:
        limit: Maximum number of facts to return (default 100).
        category: Optional category filter.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        List of KnowledgeSearchResult objects.
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    results = service.list_facts(limit=limit, category=category)
    return results


@router.delete("/facts")
async def delete_facts(
    request: DeleteFactsRequest,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Delete specific facts by their IDs.

    Args:
        request: Request body containing list of fact IDs to delete.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Confirmation message with count of deleted facts.

    Raises:
        HTTPException: 500 if deletion failed (e.g., ChromaDB unavailable).
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    success = service.delete_facts(request.ids)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete facts — knowledge store may be unavailable",
        )
    return {"status": "deleted", "count": len(request.ids)}

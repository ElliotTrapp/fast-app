"""FastAPI knowledge routes for searching and managing learned facts.

This module defines the REST API endpoints for Fast-App's knowledge system.
All routes are mounted under `/api/knowledge/` and follow the CLI-first architecture:
route handlers are thin wrappers that delegate to KnowledgeService.

## Endpoints

- GET    /api/knowledge/search              — Semantic search across user's knowledge base
- GET    /api/knowledge/facts                — List facts with optional category filter
- DELETE /api/knowledge/facts                — Delete facts by IDs
- DELETE /api/knowledge/facts/all            — Delete ALL facts for the current user
- POST   /api/knowledge/extract-from-profile — Extract facts from profile data via LLM

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
from ..log import logger
from ..models.db_models import User
from ..models.knowledge import FactCreate, FactUpdate, KnowledgeSearchResult
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


@router.delete("/facts/all")
async def delete_all_facts(
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Delete ALL facts in the user's knowledge collection.

    Used when a user imports a new profile and wants to start fresh
    with their knowledge base. This operation is irreversible.

    Args:
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Dict with status and count of deleted facts.

    Raises:
        HTTPException: 503 if ChromaDB is unavailable.
    """
    user_id = _resolve_user_id(user)
    try:
        service = _get_service(user_id)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge features unavailable — ChromaDB not installed. "
            "Install with: pip install -e '.[knowledge]'",
        )

    count = service.delete_all_facts()
    return {"status": "deleted", "count": count}


class ExtractFromProfileRequest(BaseModel):
    """Request body for extracting facts from profile data."""

    profile_data: dict = Field(
        ...,
        description="Full profile JSON data (same format as stored in profile_data column)",
    )


@router.post("/extract-from-profile")
async def extract_from_profile(
    request: ExtractFromProfileRequest,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Extract facts from profile data using LLM and store in knowledge base.

    This is the webapp equivalent of the CLI's `--extract-facts` flag on
    `profile import`. It takes profile data, runs fact extraction via LLM,
    and stores the extracted facts in the user's ChromaDB collection.

    Args:
        request: Request body containing profile_data dict.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Dict with status, fact_count, and summary of extracted facts.

    Raises:
        HTTPException: 503 if LLM or ChromaDB dependencies are unavailable.
        HTTPException: 500 if fact extraction fails.
    """
    user_id = _resolve_user_id(user)

    try:
        from ..services.fact_extractor import FactExtractor
        from ..services.llm_service import LLMService
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM dependencies not installed. "
            "Install with: pip install -e '.[llm,knowledge]'",
        )

    try:
        config = load_config()
        llm_service = LLMService(config)
        extractor = FactExtractor(llm_service)
        result = extractor.extract_facts_from_profile(request.profile_data)
    except Exception as e:
        logger.error(f"Fact extraction from profile failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fact extraction failed: {e}",
        )

    try:
        service = _get_service(user_id)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge features unavailable — ChromaDB not installed. "
            "Install with: pip install -e '.[knowledge]'",
        )

    if result.facts:
        stored_ids = service.store_facts(
            result.facts,
            source="profile_import",
        )
        logger.info(f"Stored {len(stored_ids)} facts from profile extraction for user {user_id}")
    else:
        logger.info(f"No extractable facts found in profile for user {user_id}")

    return {
        "status": "extracted",
        "fact_count": len(result.facts),
        "summary": result.summary,
    }


@router.post("/facts", status_code=status.HTTP_201_CREATED)
async def add_fact(
    fact: FactCreate,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Add a new fact to the user's knowledge collection.

    Args:
        fact: FactCreate schema with content, category, source, job_url, confidence.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Dict with id, content, category, source, job_url, confidence, created_at.
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    result = service.add_fact(user_id, fact)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add fact — knowledge store may be unavailable",
        )
    return result


@router.put("/facts/{fact_id}")
async def update_fact(
    fact_id: str,
    fact: FactUpdate,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Update an existing fact by ID.

    ChromaDB has no native update, so the old fact is deleted and re-inserted
    with updated fields. The UUID changes on update.

    Args:
        fact_id: The ID of the fact to update.
        fact: FactUpdate schema with optional fields to update.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Updated fact dict with new id, content, category, etc.

    Raises:
        HTTPException: 404 if fact not found.
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    result = service.update_fact(user_id, fact_id, fact)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fact not found",
        )
    return result


@router.get("/categories", response_model=list[str])
async def get_categories(
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Get unique categories from the user's knowledge collection.

    Args:
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        Sorted list of unique category strings.
    """
    user_id = _resolve_user_id(user)
    service = _get_service(user_id)
    return service.get_categories(user_id)

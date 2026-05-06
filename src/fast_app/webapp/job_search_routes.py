"""FastAPI routes for job search via JSearch API.

Provides endpoints for searching jobs and normalizing results.
Requires FAST_APP_JSEARCH_API_KEY to be configured.

## Endpoints

- POST /api/jobs/search  — Search for jobs by keyword and location

## Auth-Disabled Mode

When FAST_APP_JWT_SECRET is not set and no users exist in the database,
authentication is disabled. In this mode, user_id defaults to 1.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..config import load_config
from ..db import SessionDep
from ..models.db_models import User
from ..services.auth import get_current_user
from ..services.jsearch_service import JSearchService

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_DEFAULT_USER_ID = 1


def _resolve_user_id(user: User | None) -> int:
    if user is None:
        return _DEFAULT_USER_ID
    return user.id


class JobSearchRequest(BaseModel):
    """Request body for job search."""

    query: str = Field(..., min_length=1, description="Job search keywords")
    location: str = Field(default="", description="Location filter (e.g., 'San Francisco, CA')")
    num_pages: int = Field(default=1, ge=1, le=10, description="Number of result pages")
    date_posted: str = Field(
        default="",
        description="Filter: 'all', 'today', '3days', 'week', 'month'",
    )
    job_type: str = Field(
        default="",
        description="Filter: 'all', 'fulltime', 'parttime', 'contract', 'internship'",
    )
    remote: bool = Field(default=False, description="Filter for remote jobs only")


class JobSearchResponse(BaseModel):
    """Response body for job search."""

    jobs: list[dict] = Field(default_factory=list, description="List of normalized job results")
    total: int = Field(default=0, description="Total number of results returned")
    query: str = Field(default="", description="The search query used")


@router.post("/search", response_model=JobSearchResponse)
async def search_jobs(
    request: JobSearchRequest,
    session: SessionDep,
    user: User | None = Depends(get_current_user),
):
    """Search for jobs matching the query and filters.

    Uses the JSearch API (RapidAPI) which aggregates Google for Jobs,
    including LinkedIn, Indeed, Glassdoor, and more.

    Args:
        request: JobSearchRequest with query, location, and filters.
        user: Current authenticated user (None if auth disabled).
        session: Database session from dependency injection.

    Returns:
        JobSearchResponse with list of normalized job results.

    Raises:
        HTTPException: 400 if query is empty.
        HTTPException: 503 if JSearch API key is not configured.
        HTTPException: 502 if JSearch API request fails.
    """
    config = load_config()

    try:
        service = JSearchService(config)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job search is not available — requests library not installed",
        )

    try:
        jobs = service.search_jobs(
            query=request.query,
            location=request.location,
            num_pages=request.num_pages,
            date_posted=request.date_posted,
            job_type=request.job_type,
            remote=request.remote,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        )

    return JobSearchResponse(
        jobs=jobs,
        total=len(jobs),
        query=request.query,
    )

"""JSearch job search service via RapidAPI.

Searches for jobs using the JSearch API (Google for Jobs aggregator).
Returns structured job data including title, company, location, salary,
description, and apply links.

Requires a RapidAPI key set via FAST_APP_JSEARCH_API_KEY env var or
config.json jsearch.api_key.

See: https://rapidapi.com/letscrape-6bEBa3ghgh/api/jsearch
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..log import logger


class JSearchService:
    """Searches for jobs via the JSearch API (RapidAPI).

    Attributes:
        config: Application config containing JSearchConfig.
        _api_key: The RapidAPI key for authentication.
    """

    def __init__(self, config: Config):
        self.config = config
        self._api_key = config.jsearch.api_key

    def search_jobs(
        self,
        query: str,
        location: str = "",
        num_pages: int = 1,
        date_posted: str = "",
        job_type: str = "",
        remote: bool = False,
    ) -> list[dict[str, Any]]:
        """Search for jobs matching the query and filters.

        Args:
            query: Job search keywords (e.g., "python developer").
            location: Location filter (e.g., "San Francisco, CA").
            num_pages: Number of result pages (1-10, each ~10 jobs).
            date_posted: Filter by date: "all", "today", "3days", "week", "month".
            job_type: Filter by type: "all", "fulltime", "parttime", "contract", "internship".
            remote: Filter for remote/work-from-home jobs only.

        Returns:
            List of job dicts with standardized fields.

        Raises:
            ValueError: If no API key is configured.
            RuntimeError: If the API request fails.
        """
        if not self._api_key:
            raise ValueError(
                "JSearch API key not configured. "
                "Set FAST_APP_JSEARCH_API_KEY env var or jsearch.api_key in config.json"
            )

        import requests

        search_query = query
        if location:
            search_query = f"{query} in {location}"

        params: dict[str, Any] = {
            "query": search_query,
            "page": 1,
            "num_pages": min(num_pages, 10),
        }
        if date_posted:
            params["date_posted"] = date_posted
        if job_type:
            params["employment_type"] = job_type
        if remote:
            params["work_from_home"] = "true"

        headers = {
            "x-rapidapi-key": self._api_key,
            "x-rapidapi-host": "jsearch.p.rapidapi.com",
        }

        logger.api_request(f"JSearch: query={search_query!r}, params={params}")

        try:
            response = requests.get(
                f"{self.config.jsearch.base_url}/search",
                headers=headers,
                params=params,
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"JSearch API request failed: {e}")
            raise RuntimeError(f"Job search failed: {e}") from e

        data = response.json()
        raw_jobs = data.get("data", [])

        jobs = [self._normalize_job(j) for j in raw_jobs]
        logger.info(f"JSearch returned {len(jobs)} jobs for query={search_query!r}")

        return jobs

    def _normalize_job(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a JSearch result into a standardized job dict.

        Args:
            raw: Raw job dict from JSearch API.

        Returns:
            Normalized dict with consistent key names.
        """
        return {
            "id": raw.get("job_id", ""),
            "title": raw.get("job_title", ""),
            "company": raw.get("employer_name", ""),
            "company_logo": raw.get("employer_logo", ""),
            "company_website": raw.get("employer_website", ""),
            "location": self._format_location(raw),
            "is_remote": raw.get("job_is_remote", False),
            "description": raw.get("job_description", ""),
            "salary_min": raw.get("job_min_salary"),
            "salary_max": raw.get("job_max_salary"),
            "salary_currency": raw.get("job_salary_currency", ""),
            "salary_period": raw.get("job_salary_period", ""),
            "job_type": raw.get("job_employment_type", ""),
            "posted_date": raw.get("job_posted_human_readable", ""),
            "apply_link": raw.get("job_apply_link", ""),
            "apply_is_direct": raw.get("job_apply_is_direct", False),
            "publisher": raw.get("job_publisher", ""),
            "required_skills": raw.get("job_required_skills", ""),
            "required_experience": raw.get("job_required_experience", ""),
            "required_education": raw.get("job_required_education", ""),
            "job_url": raw.get("job_apply_link", ""),
        }

    @staticmethod
    def _format_location(raw: dict[str, Any]) -> str:
        """Format location from raw JSearch data.

        Args:
            raw: Raw job dict from JSearch API.

        Returns:
            Human-readable location string.
        """
        parts = []
        if raw.get("job_city"):
            parts.append(raw["job_city"])
        if raw.get("job_state"):
            parts.append(raw["job_state"])
        if raw.get("job_country"):
            parts.append(raw["job_country"])
        return ", ".join(parts) if parts else "Remote"

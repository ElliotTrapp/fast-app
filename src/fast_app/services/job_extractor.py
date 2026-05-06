"""Job data extraction with multi-strategy URL fetching and direct text input.

This module provides the JobExtractor class, which can extract structured job data
from URLs or raw text using multiple fetching strategies and LLM parsing.

## Fetching Strategies (tried in order)

1. **Workday CXS API**: Direct JSON API for myworkdayjobs.com URLs — no browser needed.
2. **HTTP requests**: Standard HTTP GET with requests library for static sites.
3. **Ollama web_fetch**: Fallback for sites that need special handling.

## Direct Text Input

The `extract_from_text()` method accepts a job description string directly,
enabling pasting of job descriptions that can't be fetched from URLs.

See: docs/adr/001-llm-abstraction-langchain.md
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from ollama import Client

from ..log import logger
from ..models import JobData
from ..utils.async_helpers import run_async
from ..utils.spinner import SpinnerContextManager
from ..utils.text import strip_markdown_json


def _is_workday_url(url: str) -> bool:
    """Check if a URL is a Workday job posting URL.

    Workday URLs follow the pattern:
        https://{tenant}.wd{N}.myworkdayjobs.com/{locale}/{site_id}/...

    Examples:
        https://argonne.wd1.myworkdayjobs.com/en-US/Argonne_Careers/details/...
        https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/...
    """
    return "myworkdayjobs.com" in url.lower()


def _parse_workday_url(url: str) -> tuple[str, str, str] | None:
    """Parse a Workday URL into (tenant, host, site_id) components.

    Returns None if the URL doesn't match the expected pattern.
    """
    try:
        parsed = urlparse(url)
        host = parsed.netloc
        if "myworkdayjobs.com" not in host:
            return None

        tenant = host.split(".")[0]
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        # Find site_id — skip locale prefix (e.g., "en-US") if present
        site_id = ""
        for part in path_parts:
            if part == "en-US" or part == "en-GB" or "-" in part and len(part) <= 5:
                continue
            if not site_id:
                site_id = part
                break

        if not site_id:
            # Fallback: use "External" as common default
            site_id = "External"

        return tenant, host, site_id
    except Exception:
        return None


def _fetch_workday_cxs(tenant: str, host: str, site_id: str, job_url: str) -> str | None:
    """Fetch job data from Workday's CXS (Candidate Experience Service) API.

    Workday exposes a public JSON API that returns structured job data without
    needing a browser. This approach:
    - Works for all modern Workday tenant deployments
    - Doesn't require authentication
    - Returns structured JSON with full job descriptions
    - Handles the redirect/404 that Ollama web_fetch encounters

    Returns:
        Job description text (HTML stripped to plain text) or None if the API fails.
    """
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; Workday CXS API unavailable")
        return None

    # Step 1: Extract the job path from the full URL
    # e.g., /en-US/Argonne_Careers/details/Scientific-Data-Services-Engineer---AI---HPC_422640
    parsed = urlparse(job_url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]

    # Find the job detail path — skip locale and site_id
    job_path = None
    for i, part in enumerate(path_parts):
        if part == site_id:
            remaining = "/".join(path_parts[i + 1 :])
            if remaining:
                job_path = "/" + remaining
            break

    if not job_path:
        # Try to get a list of jobs via search, then find the specific one
        pass

    # Step 2: Try to fetch the job detail directly
    if job_path:
        detail_url = f"https://{host}/wday/cxs/{tenant}/{site_id}{job_path}"
        headers = {
            "Accept": "application/json",
            "Origin": f"https://{host}",
            "Referer": f"https://{host}/",
        }
        try:
            response = requests.get(detail_url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                job_info = data.get("jobPostingInfo", data)
                title = data.get("title", job_info.get("title", ""))
                description = job_info.get("jobDescription", "")
                # Strip HTML tags from description
                description = re.sub(r"<[^>]+>", " ", description)
                description = re.sub(r"\s+", " ", description).strip()

                if description:
                    logger.info("Workday CXS API: successfully fetched job detail")
                    return f"Title: {title}\n\nContent:\n{description}"
        except Exception as e:
            logger.warning(f"Workday CXS detail fetch failed: {e}")

    # Step 3: Fallback — search for the job via the search API
    search_url = f"https://{host}/wday/cxs/{tenant}/{site_id}/jobs"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/",
    }

    # Extract search keywords from the URL (job title slug)
    search_text = ""
    # Try to extract meaningful keywords from the URL path
    for part in path_parts:
        if "-" in part and len(part) > 10:
            # Likely a job title slug like "Scientific-Data-Services-Engineer---AI---HPC"
            search_text = part.replace("---", " ").replace("--", " ").replace("-", " ")
            break

    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": search_text,
    }

    try:
        response = requests.post(search_url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            job_postings = data.get("jobPostings", [])

            if job_postings:
                # Take the first matching result
                job = job_postings[0]
                title = job.get("title", "")

                # Fetch the detail page for full description
                external_path = job.get("externalPath", "")
                if external_path:
                    detail_url = f"https://{host}/wday/cxs/{tenant}/{site_id}{external_path}"
                    detail_headers = {"Accept": "application/json"}
                    detail_resp = requests.get(detail_url, headers=detail_headers, timeout=15)
                    if detail_resp.status_code == 200:
                        detail_data = detail_resp.json()
                        job_info = detail_data.get("jobPostingInfo", detail_data)
                        description = job_info.get("jobDescription", "")
                        description = re.sub(r"<[^>]+>", " ", description)
                        description = re.sub(r"\s+", " ", description).strip()

                        if description:
                            logger.info("Workday CXS API: fetched job via search + detail")
                            loc = job.get("locationsText", "")
                            return f"Title: {title}\n\nContent:\n{description}\n\nLocation: {loc}"

                # If we can't get the detail, use what we have from the listing
                locations = job.get("locationsText", "")
                bullet_fields = job.get("bulletFields", [])
                content = f"Title: {title}\n\nContent:\nJob posting found on Workday."
                if locations:
                    content += f"\nLocation: {locations}"
                if bullet_fields:
                    content += f"\nDetails: {', '.join(bullet_fields)}"

                logger.info("Workday CXS API: fetched job listing (limited detail)")
                return content

    except Exception as e:
        logger.warning(f"Workday CXS search API failed: {e}")

    return None


def _fetch_with_requests(url: str) -> str | None:
    """Fetch page content using the requests library.

    This handles static HTML sites that don't require JavaScript rendering.
    Includes headers to mimic a browser for sites that block plain HTTP clients.
    """
    try:
        import requests as req_lib
    except ImportError:
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = req_lib.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return None

        html = response.text

        # Extract title
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Strip HTML tags for a cleaner text extraction
        # Remove script and style blocks first
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove all HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Decode HTML entities
        import html as html_lib

        text = html_lib.unescape(text)

        if len(text) < 100:
            # Not enough content to be useful
            return None

        logger.info("HTTP requests: successfully fetched page content")
        return f"Title: {title}\n\nContent:\n{text}"

    except Exception as e:
        logger.warning(f"HTTP requests fetch failed: {e}")
        return None


class JobExtractor:
    """Extract job data from URLs or raw text using multi-strategy fetching and LLM.

    Fetching strategies (tried in order):
    1. Workday CXS API (for myworkdayjobs.com URLs)
    2. HTTP requests (for static HTML sites)
    3. Ollama web_fetch (fallback)

    Also supports direct text input via extract_from_text().
    """

    def __init__(self, client: Client, model: str):
        self.client = client
        self.model = model

    def _extract_job_data_from_content(self, content: str, url: str = "") -> dict[str, Any]:
        """Extract structured job data from text content using LLM.

        This is the shared extraction logic used by both URL and text input paths.

        Args:
            content: The page content or pasted job description text.
            url: Optional URL for metadata (site, ID).

        Returns:
            Dict with JobData fields populated from content.
        """
        schema = (
            '{"title": "string", "company": "string", '
            '"location": "string or null", "description": "string or null", '
            '"min_amount": "number or null", "max_amount": "number or null", '
            '"currency": "string or null", "interval": "string or null", '
            '"job_type": "string or null", "is_remote": "boolean or null", '
            '"job_level": "string or null", "job_function": "string or null", '
            '"skills": "string or null", "company_industry": "string or null", '
            '"company_url": "string or null", "company_description": "string or null", '
            '"company_num_employees": "string or null"}'
        )

        prompt = f"""Extract job posting information from this page content and return as JSON.

Page Content:
{content}

Return JSON with these fields (omit fields you cannot find):
- title: Job title
- company: Company name
- location: Job location (city, state/country)
- description: Full job description text
- min_amount: Minimum salary (number only, no currency symbol)
- max_amount: Maximum salary (number only, no currency symbol)
- currency: Currency code (USD, EUR, etc.)
- interval: "yearly" or "hourly"
- job_type: "fulltime", "parttime", "contract", or "internship"
- is_remote: true if remote work allowed
- job_level: Seniority level (Junior, Mid, Senior, Lead, Principal)
- job_function: Department (Engineering, Marketing, Sales, etc.)
- skills: Comma-separated list of required skills
- company_industry: Industry sector
- company_url: Company website
- company_description: Brief company description
- company_num_employees: Employee count range (e.g., "51-200", "10000+")

Return valid JSON matching this schema:
{schema}
"""

        logger.llm_call(
            "extract_job_data",
            {
                "url": url[:60] + "..." if len(url) > 60 else url or "text input",
                "content_length": len(content),
            },
        )

        response = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            format=JobData.model_json_schema(),
            think=False,
            options={"temperature": 0, "num_predict": 2000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        extracted = JobData.model_validate_json(cleaned).model_dump()

        url_hash = hashlib.md5((url or content[:200]).encode()).hexdigest()[:12]

        job_data = {
            "id": url_hash,
            "job_url": url or "",
            "job_url_direct": None,
            "site": url.split("/")[2] if url and "/" in url else "text_input",
            **extracted,
        }

        logger.llm_result(
            "job_data",
            {
                "id": job_data["id"],
                "title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
                "location": job_data.get("location", "Unknown"),
            },
        )

        return job_data

    async def _extract_from_url_async(self, url: str) -> dict[str, Any]:
        """Async version of job extraction with multi-strategy fetching.

        Tries fetching strategies in order:
        1. Workday CXS API (for myworkdayjobs.com URLs)
        2. HTTP requests (for static sites)
        3. Ollama web_fetch (fallback)
        """
        logger.header("Job Extraction")
        content = None

        # Strategy 1: Workday CXS API
        if _is_workday_url(url):
            logger.info("Detected Workday URL, trying CXS API...")
            parts = _parse_workday_url(url)
            if parts:
                tenant, host, site_id = parts
                content = await asyncio.to_thread(_fetch_workday_cxs, tenant, host, site_id, url)
                if content:
                    return self._extract_job_data_from_content(content, url)
                logger.warning("Workday CXS API failed, trying fallback strategies...")

        # Strategy 2: HTTP requests
        content = await asyncio.to_thread(_fetch_with_requests, url)
        if content and len(content) > 200:
            return self._extract_job_data_from_content(content, url)
        logger.info(
            "HTTP requests fetch failed or returned insufficient content, "
            "trying Ollama web_fetch..."
        )

        # Strategy 3: Ollama web_fetch (original approach)
        try:
            logger.api_request("WEB_FETCH", url)
            fetched = await asyncio.to_thread(self.client.web_fetch, url)
            content = f"Title: {fetched.title}\n\nContent:\n{fetched.content}"
            logger.api_response(200)
            logger.llm_response(len(content), f"{fetched.title}")
        except Exception as e:
            logger.error(f"All fetching strategies failed for URL: {url}")
            logger.error(f"Ollama web_fetch error: {e}")
            raise RuntimeError(f"Failed to fetch job data from URL: {url}") from e

        return self._extract_job_data_from_content(content, url)

    async def _extract_from_text_async(
        self, title: str, content: str, url: str = ""
    ) -> dict[str, Any]:
        """Extract job data from pasted text content.

        Args:
            title: The job title (user-provided or from paste header).
            content: The raw job description text.
            url: Optional URL for metadata.

        Returns:
            Dict with JobData fields populated from the text.
        """
        logger.header("Job Extraction (Text Input)")
        formatted = f"Title: {title}\n\nContent:\n{content}"
        return self._extract_job_data_from_content(formatted, url)

    def extract_from_url(self, url: str) -> dict[str, Any]:
        """Fetch and parse job posting URL using multi-strategy fetching.

        Tries Workday CXS API, then HTTP requests, then Ollama web_fetch.

        Args:
            url: Job posting URL.

        Returns:
            Dict with JobData fields populated from URL content.

        Raises:
            RuntimeError: If all fetching strategies fail.
        """
        with SpinnerContextManager("🔍 Extracting job data "):
            try:
                result = run_async(self._extract_from_url_async(url))
                return result
            except Exception as e:
                logger.error(f"Failed to extract job data: {e}")
                raise RuntimeError(f"Failed to extract job data: {e}") from e

    def extract_from_text(self, title: str, content: str, url: str = "") -> dict[str, Any]:
        """Extract job data from pasted text content.

        This is the alternative entry point for when the user pastes a job
        description directly instead of providing a URL. Useful for:
        - URLs that can't be fetched (JavaScript-heavy sites, paywalled content)
        - Manually copied job descriptions
        - Job descriptions from email or other non-web sources

        Args:
            title: The job title (e.g., "Software Engineer at Acme Corp").
            content: The raw job description text.
            url: Optional original URL for metadata (stored but not fetched).

        Returns:
            Dict with JobData fields populated from the text content.
        """
        with SpinnerContextManager("🔍 Extracting job data from text "):
            try:
                result = run_async(self._extract_from_text_async(title, content, url))
                return result
            except Exception as e:
                logger.error(f"Failed to extract job data from text: {e}")
                raise RuntimeError(f"Failed to extract job data from text: {e}") from e

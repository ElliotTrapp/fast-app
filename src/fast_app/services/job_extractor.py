"""Job data extraction using Ollama web_fetch."""

import hashlib
import re
from typing import Dict, Any
from ollama import Client

from ..models import JobData
from ..log import logger


class JobExtractor:
    """Extract job data from URLs using Ollama web_fetch and LLM."""

    def __init__(self, client: Client, model: str):
        self.client = client
        self.model = model

    def _strip_markdown_json(self, content: str) -> str:
        """Strip markdown code blocks from LLM response if present."""
        content = content.strip()
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    def extract_from_url(self, url: str) -> Dict[str, Any]:
        """Fetch and parse job posting URL.

        Args:
            url: Job posting URL

        Returns:
            Dict with JobData fields populated from URL content
        """
        logger.header("Job Extraction")
        logger.api_request("WEB_FETCH", url)

        try:
            fetched = self.client.web_fetch(url)
            content = f"Title: {fetched.title}\n\nContent:\n{fetched.content}"
            logger.api_response(200)
            logger.llm_response(len(content), f"{fetched.title}")
        except Exception as e:
            logger.error(f"Failed to fetch URL content: {e}")
            raise RuntimeError(f"Failed to fetch URL content: {e}")

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
{{"title": "string", "company": "string", "location": "string or null", "description": "string or null", "min_amount": "number or null", "max_amount": "number or null", "currency": "string or null", "interval": "string or null", "job_type": "string or null", "is_remote": "boolean or null", "job_level": "string or null", "job_function": "string or null", "skills": "string or null", "company_industry": "string or null", "company_url": "string or null", "company_description": "string or null", "company_num_employees": "string or null"}}
"""

        logger.llm_call(
            "extract_job_data",
            {
                "url": url[:60] + "..." if len(url) > 60 else url,
                "content_length": len(content),
            },
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format=JobData.model_json_schema(),
                think=False,
                options={"temperature": 0, "num_predict": 2000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)

            logger.llm_response(len(cleaned))

            extracted = JobData.model_validate_json(cleaned).model_dump()

            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]

            job_data = {
                "id": url_hash,
                "job_url": url,
                "job_url_direct": None,
                "site": url.split("/")[2] if "/" in url else "unknown",
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

        except Exception as e:
            logger.error(f"Failed to extract job data: {e}")
            raise RuntimeError(f"Failed to extract job data: {e}")

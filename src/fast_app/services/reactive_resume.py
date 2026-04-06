"""Reactive Resume API client."""

from typing import Dict, Any, Optional
import requests
import json

from ..log import logger


class ReactiveResumeClient:
    """Client for Reactive Resume API."""

    def __init__(self, endpoint: str, api_key: str):
        self.base_url = endpoint.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
        }

    def test_connection(self) -> bool:
        """Test connection to Reactive Resume API."""
        try:
            response = requests.get(
                self.base_url,
                headers=self.headers,
                timeout=10,
            )
            logger.api_response(response.status_code)
            return response.status_code in (200, 401, 302, 303)
        except requests.RequestException as e:
            logger.error(f"Connection error: {e}")
            return False

    def list_resumes(self) -> list:
        """List all resumes.

        Returns:
            List of resume objects
        """
        try:
            url = f"{self.base_url}/api/openapi/resumes"
            logger.api_request("GET", url)

            response = requests.get(
                url,
                headers=self.headers,
                timeout=30,
            )

            logger.api_response(response.status_code)

            if response.status_code >= 400:
                return []

            result = response.json()

            # Handle different response formats
            if isinstance(result, list):
                return result
            elif isinstance(result, dict):
                return result.get("data", result.get("resumes", []))

            return []

        except (requests.RequestException, json.JSONDecodeError):
            return []

    def get_resume(self, resume_id: str) -> Optional[Dict[str, Any]]:
        """Get resume by ID.

        Args:
            resume_id: Resume ID

        Returns:
            Resume object if found, None otherwise
        """
        try:
            url = f"{self.base_url}/api/openapi/resumes/{resume_id}"
            logger.api_request("GET", url)

            response = requests.get(
                url,
                headers=self.headers,
                timeout=30,
            )

            logger.api_response(response.status_code)

            if response.status_code == 404:
                return None

            if response.status_code >= 400:
                return None

            return response.json()

        except (requests.RequestException, json.JSONDecodeError):
            return None

    def find_resume_by_title(self, title: str) -> Optional[str]:
        """Find a resume by title and return its ID if found.

        Args:
            title: Resume title to search for

        Returns:
            Resume ID if found, None otherwise
        """
        resumes = self.list_resumes()

        for resume in resumes:
            if isinstance(resume, dict):
                if resume.get("title") == title:
                    resume_id = resume.get("id")
                    if resume_id:
                        logger.cache_hit("resume_by_title", f"id={resume_id}")
                        return str(resume_id)

        return None

    def create_resume(self, title: str, tags: list = None) -> str:
        """Create a new resume with title.

        Args:
            title: Resume title
            tags: List of tags (optional)

        Returns:
            Resume ID

        Raises:
            RuntimeError: If creation fails
        """
        try:
            url = f"{self.base_url}/api/openapi/resumes"

            # Generate slug from title
            slug = title.lower().replace(" ", "-").replace("/", "-")[:50]

            payload = {
                "name": title,
                "slug": slug,
                "tags": tags or [],
            }

            logger.api_request("POST", url)
            logger.detail("name", title)
            logger.detail("slug", slug)
            logger.detail("tags", tags or [])

            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 401:
                raise RuntimeError("Authentication failed. Check your API key.")

            if response.status_code >= 400:
                error_detail = response.text if response.content else "Unknown error"
                raise RuntimeError(f"Failed to create resume: {error_detail}")

            response.raise_for_status()

            logger.api_response(response.status_code)

            result = response.json()

            # Result is just the resume ID string
            resume_id = result if isinstance(result, str) else result.get("id")

            if not resume_id:
                raise RuntimeError(f"Failed to get resume ID from response: {result}")

            logger.success(f"Resume created: {resume_id}")

            return str(resume_id)

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to create resume: {e}")

    def update_resume(self, resume_id: str, resume_data: Dict[str, Any]) -> bool:
        """Update a resume with data.

        Args:
            resume_id: Resume ID
            resume_data: Resume data

        Returns:
            True if updated successfully

        Raises:
            RuntimeError: If update fails
        """
        try:
            url = f"{self.base_url}/api/openapi/resumes/{resume_id}"

            logger.api_request("PUT", url)
            logger.detail("data_keys", list(resume_data.keys()))

            response = requests.put(
                url,
                headers=self.headers,
                json={"data": resume_data},
                timeout=30,
            )

            if response.status_code == 401:
                raise RuntimeError("Authentication failed. Check your API key.")

            if response.status_code == 404:
                raise RuntimeError(f"Resume {resume_id} not found")

            if response.status_code >= 400:
                error_detail = response.text if response.content else "Unknown error"
                raise RuntimeError(f"Failed to update resume: {error_detail}")

            response.raise_for_status()

            logger.api_response(response.status_code)
            logger.success(f"Resume updated: {resume_id}")

            return True

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to update resume: {e}")

    def delete_resume(self, resume_id: str) -> bool:
        """Delete a resume by ID.

        Args:
            resume_id: Resume ID to delete

        Returns:
            True if deleted successfully
        """
        try:
            url = f"{self.base_url}/api/openapi/resumes/{resume_id}"
            logger.api_request("DELETE", url)

            response = requests.delete(
                url,
                headers=self.headers,
                timeout=30,
            )

            logger.api_response(response.status_code)

            if response.status_code == 404:
                logger.warning(f"Resume {resume_id} not found (already deleted?)")
                return True

            return response.status_code < 400

        except requests.RequestException:
            return False

    def get_resume_url(self, resume_id: str) -> str:
        """Return the URL to view/edit the resume.

        Args:
            resume_id: Resume ID returned from import

        Returns:
            Full URL to edit the resume
        """
        return f"{self.base_url}/builder/{resume_id}"

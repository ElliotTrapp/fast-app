"""Resume utility functions."""

import copy
import uuid
from typing import Any


def merge_resume_with_base(
    generated: dict[str, Any], base: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge generated resume data with base template.

    The base template provides styling/theme settings, generated data
    provides the content.

    Args:
        generated: Generated resume data from LLM
        base: Base resume template (optional)

    Returns:
        Merged resume data
    """
    if not base:
        return generated

    result = copy.deepcopy(base)

    # Override basics with generated content
    if "basics" in generated:
        result["basics"] = generated["basics"]

    # Override summary with generated content
    if "summary" in generated:
        result["summary"] = generated["summary"]

    # Merge sections
    if "sections" in generated:
        for section_name, section_data in generated["sections"].items():
            if section_name in result.get("sections", {}):
                # Merge items, preferring generated content
                result["sections"][section_name] = section_data
            else:
                # Add new section
                result.setdefault("sections", {})[section_name] = section_data

    # Preserve metadata from base if exists
    if "metadata" in base:
        result.setdefault("metadata", base["metadata"])

    return result


def merge_cover_letter_with_base(
    generated: dict[str, Any],
    profile: dict[str, Any],
    base: dict[str, Any] | None,
    job_title: str,
    company: str,
) -> dict[str, Any]:
    """Merge generated cover letter content with base template.

    The base template provides styling/theme settings, generated data
    provides the recipient and content.

    Args:
        generated: Generated cover letter data from LLM
        profile: User profile data
        base: Base cover letter template (optional)
        job_title: Job title for the cover letter
        company: Company name for the cover letter

    Returns:
        Merged cover letter data
    """
    if not base:
        # Create minimal structure
        return {
            "basics": profile.get("basics", {}),
            "summary": {"content": generated.get("content", "")},
            "metadata": {"notes": f"Cover letter for {job_title} at {company}"},
            "sections": {},
        }

    result = copy.deepcopy(base)

    # Override summary content with cover letter
    result["summary"] = {"content": generated.get("content", "")}

    # Preserve metadata from base if exists
    if "metadata" in base:
        result.setdefault("metadata", base["metadata"])

    return result


def check_existing_resume(
    rr_client,  # ReactiveResumeClient
    cache,  # CacheManager
    job_dir,
    resume_title: str,
    overwrite: bool,
) -> str | None:
    """Check for existing resume/cover letter and handle --overwrite flag.

    Args:
        rr_client: Reactive Resume client
        cache: Cache manager
        job_dir: Job directory
        resume_title: Title of the resume/cover letter
        overwrite: Whether to overwrite existing

    Returns:
        Resume ID if one exists (or None if deleted)

    Raises:
        click.ClickException: If resume exists and overwrite is False
    """
    cached_reactive = cache.get_cached_reactive_resume(job_dir)
    existing_id: str | None = None

    if cached_reactive:
        existing_id = cached_reactive.get("resume_id")
        if existing_id:
            resume_check = rr_client.get_resume(existing_id)
            if not resume_check:
                existing_id = None

    if not existing_id:
        existing_id = rr_client.find_resume_by_title(resume_title)

    if existing_id and overwrite:
        import click
        from ..log import logger

        logger.warning(f"Deleting existing resume: {existing_id}")
        rr_client.delete_resume(existing_id)
        return None

    return existing_id

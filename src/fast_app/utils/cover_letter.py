"""Cover letter specific utilities."""

import copy
from typing import Any

import click

from ..log import logger


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
        generated: Generated cover letter data from LLM (has 'recipient' and 'content' keys)
        profile: User profile data
        base: Base cover letter template (optional)
        job_title: Job title for the cover letter
        company: Company name for the cover letter

    Returns:
        Merged cover letter data ready for Reactive Resume

    Raises:
        ValueError: If content is missing or empty
    """
    # Extract the actual cover letter text - validate it exists
    cover_letter_content = generated.get("content", "")

    if not cover_letter_content or not cover_letter_content.strip():
        raise ValueError(
            f"Cover letter content is empty. Generated data keys: {list(generated.keys())}"
        )

    if not base:
        # Create minimal structure with all required fields for Reactive Resume
        return {
            "basics": profile.get("basics", {}),
            "summary": {
                "title": f"Cover Letter for {job_title} at {company}",
                "content": cover_letter_content,
                "columns": 1,
                "hidden": False,
            },
            "sections": {},
            "metadata": {"notes": f"Cover letter for {job_title} position at {company}"},
        }

    result = copy.deepcopy(base)

    # Override summary content with cover letter
    result["summary"] = {
        "title": f"Cover Letter for {job_title} at {company}",
        "content": cover_letter_content,
        "columns": base.get("summary", {}).get("columns", 1),
        "hidden": False,
    }

    # Preserve metadata from base if exists
    if "metadata" in base:
        result.setdefault("metadata", base["metadata"])

    return result


def check_existing_cover_letter(
    rr_client,  # ReactiveResumeClient
    cache,  # CacheManager
    job_dir,
    overwrite: bool,
) -> str | None:
    """Check for existing cover letter and handle --overwrite flag.

    Uses the cover_letter_id from cache to check if it still exists in Reactive Resume.
    Does NOT search by title - uses direct ID lookup.

    Args:
        rr_client: Reactive Resume client
        cache: Cache manager
        job_dir: Job directory
        overwrite: Whether to overwrite existing

    Returns:
        Cover letter ID if one exists (and should be deleted), None otherwise

    Raises:
        click.ClickException: If cover letter exists and overwrite is False
    """
    cached_cover_letter = cache.get_cached_reactive_cover_letter(job_dir)
    existing_id: str | None = None

    # Check cache for cover letter ID
    if cached_cover_letter:
        existing_id = cached_cover_letter.get("cover_letter_id")
        if existing_id:
            # Verify it still exists using direct ID lookup
            cover_letter_check = rr_client.get_resume(existing_id)
            if not cover_letter_check:
                # ID in cache but doesn't exist - clear it
                existing_id = None

    if existing_id and not overwrite:
        logger.error(f"Cover letter already exists in Reactive Resume (ID: {existing_id})")
        click.echo(
            click.style(
                "\n❌ Error: Cover letter already exists in Reactive Resume.",
                fg="red",
            )
        )
        click.echo(
            click.style(
                f"   Cover Letter ID: {existing_id}",
                fg="yellow",
            )
        )
        click.echo(
            click.style(
                "   Use --overwrite-resume to replace it.",
                fg="yellow",
            )
        )
        raise click.ClickException(
            f"Cover letter already exists (ID: {existing_id}). Use --overwrite-resume to overwrite."
        )

    if existing_id and overwrite:
        logger.warning(f"Deleting existing cover letter: {existing_id}")
        rr_client.delete_resume(existing_id)
        return None

    return existing_id

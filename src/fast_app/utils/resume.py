"""Resume utility functions."""

import copy
from typing import Any
from ..log import logger


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


def check_existing_resume(
    rr_client,  # ReactiveResumeClient
    cache,  # CacheManager
    job_dir,
    overwrite: bool,
) -> str | None:
    """Check for existing resume and handle --overwrite flag.

    Uses the resume_id from cache to check if it still exists in Reactive Resume.
    Does NOT search by title - uses direct ID lookup.

    Args:
        rr_client: Reactive Resume client
        cache: Cache manager
        job_dir: Job directory
        overwrite: Whether to overwrite existing

    Returns:
        Resume ID if one exists (and should be deleted), None otherwise

    Raises:
        click.ClickException: If resume exists and overwrite is False
    """
    import click

    from ..log import logger

    cached_resume = cache.get_cached_reactive_resume(job_dir)
    existing_id: str | None = None

    # Check cache for resume ID
    if cached_resume:
        existing_id = cached_resume.get("resume_id")
        if existing_id:
            # Verify it still exists using direct ID lookup
            resume_check = rr_client.get_resume(existing_id)
            if not resume_check:
                # ID in cache but doesn't exist - clear it
                existing_id = None

    if existing_id and not overwrite:
        logger.error(f"Resume already exists in Reactive Resume (ID: {existing_id})")
        click.echo(
            click.style(
                "\n❌ Error: Resume already exists in Reactive Resume.",
                fg="red",
            )
        )
        click.echo(
            click.style(
                f"   Resume ID: {existing_id}",
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
            f"Resume already exists (ID: {existing_id}). Use --overwrite-resume to overwrite."
        )

    if existing_id and overwrite:
        logger.warning(f"Deleting existing resume: {existing_id}")
        rr_client.delete_resume(existing_id)
        return None

    return existing_id

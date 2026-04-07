"""Cover letter specific utilities."""

import copy
import uuid
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
    recipient = generated.get("recipient", "")

    if not cover_letter_content or not cover_letter_content.strip():
        raise ValueError(
            f"Cover letter content is empty. Generated data keys: {list(generated.keys())}"
        )

    # Generate UUIDs for the custom section and its item
    section_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())

    if not base:
        # Create minimal structure with custom section for cover letter
        return {
            "basics": profile.get("basics", {}),
            "summary": {"content": "", "columns": 1, "hidden": True},
            "sections": {},
            "customSections": [
                {
                    "title": "Cover Letter",
                    "columns": 1,
                    "hidden": False,
                    "id": section_id,
                    "type": "cover-letter",
                    "items": [
                        {
                            "id": item_id,
                            "hidden": False,
                            "recipient": recipient,
                            "content": cover_letter_content,
                        }
                    ],
                }
            ],
            "metadata": {
                "notes": f"Cover letter for {job_title} position at {company}",
                "layout": {"pages": [{"fullWidth": True, "main": [section_id], "sidebar": []}]},
            },
        }

    result = copy.deepcopy(base)

    # Populate basics from profile
    result["basics"] = profile.get("basics", {})

    # Find and update the Cover Letter custom section
    custom_sections = result.get("customSections", [])
    cover_letter_section_idx = None

    for idx, section in enumerate(custom_sections):
        if section.get("type") == "cover-letter" or section.get("title") == "Cover Letter":
            cover_letter_section_idx = idx
            break

    if cover_letter_section_idx is not None:
        # Update existing cover letter section with generated IDs
        result["customSections"][cover_letter_section_idx]["id"] = section_id
        result["customSections"][cover_letter_section_idx]["items"][0]["id"] = item_id
        result["customSections"][cover_letter_section_idx]["items"][0]["recipient"] = recipient
        result["customSections"][cover_letter_section_idx]["items"][0]["content"] = (
            cover_letter_content
        )
    else:
        # Add new cover letter section
        result.setdefault("customSections", []).append(
            {
                "title": "Cover Letter",
                "columns": 1,
                "hidden": False,
                "id": section_id,
                "type": "cover-letter",
                "items": [
                    {
                        "id": item_id,
                        "hidden": False,
                        "recipient": recipient,
                        "content": cover_letter_content,
                    }
                ],
            }
        )

    # Add the custom section to the layout pages
    metadata = result.get("metadata", {})
    layout = metadata.get("layout", {})
    pages = layout.get("pages", [])

    if pages:
        # Add section ID to first page's main section if not already there
        main = pages[0].get("main", [])
        if section_id not in main:
            main.append(section_id)
            pages[0]["main"] = main
    else:
        # Create default page with custom section
        pages = [{"fullWidth": True, "main": [section_id], "sidebar": []}]

    # Update metadata
    result.setdefault("metadata", {})["layout"] = {"pages": pages}

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

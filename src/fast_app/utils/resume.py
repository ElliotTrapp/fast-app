"""Resume utility functions."""

import copy
from typing import Any

import click

from ..log import logger
from ..models import ResumeData


def merge_resume_with_base(
    generated: dict[str, Any],
    profile: dict[str, Any],
    base: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge generated resume content with base template.

    The base template provides styling/theme settings.
    Generated data provides summary and sections from LLM.
    Profile provides basics (name, email, etc.).

    Args:
        generated: Generated resume content from LLM (has 'summary' and 'sections')
        profile: User profile data
        base: Base resume template (optional)

    Returns:
        Merged resume data ready for Reactive Resume

    Raises:
        ValueError: If merged data doesn't match ResumeData schema
    """
    if not base:
        # Create minimal structure with basics from profile
        result = {
            "basics": profile.get("basics", {}),
            "summary": generated.get("summary", {}),
            "sections": generated.get("sections", {}),
            "metadata": {},
        }
    else:
        result = copy.deepcopy(base)

        # Override basics with profile data
        result["basics"] = profile.get("basics", {})

        # Override summary with generated content
        if "summary" in generated:
            result["summary"] = generated["summary"]

        # Override sections with generated content, but preserve profiles and languages from base
        if "sections" in generated:
            result["sections"] = generated["sections"]

            # Preserve profiles section from base template
            if base.get("sections", {}).get("profiles"):
                result["sections"]["profiles"] = base["sections"]["profiles"]

            # Preserve languages section from base template
            if base.get("sections", {}).get("languages"):
                result["sections"]["languages"] = base["sections"]["languages"]

        # Preserve columns from base template
        for section_name, section_data in base.get("sections", {}).items():
            if section_name in result.get("sections", {}):
                if "columns" in section_data:
                    result["sections"][section_name]["columns"] = section_data["columns"]

    # Remove company level position and period data
    # position and period should always only come from the role level
    for section_name, section_data in result.get("sections", {}).items():
        if section_name != "experience":
            continue
        if not section_data.get("items", []):
            continue
        for company in section_data["items"]:
            company["position"] = ""
            company["period"] = ""

    # Validate the structure matches ResumeData schema
    try:
        validated = ResumeData.model_validate(result)
        logger.success("Resume data validated successfully")
        return validated.model_dump()
    except Exception as e:
        logger.error(f"Resume data validation failed: {e}")
        click.echo(click.style("\n❌ Resume data validation failed:", fg="red"))
        click.echo(click.style(f"   {str(e)}", fg="yellow"))

        # Show what we have
        click.echo(click.style("\n📊 Generated data structure:", fg="cyan"))
        click.echo(f"   Keys: {list(generated.keys())}")
        click.echo(f"   Summary: {generated.get('summary', {})}")
        click.echo(f"   Sections: {list(generated.get('sections', {}).keys())}")

        click.echo(click.style("\n📊 Profile data:", fg="cyan"))
        click.echo(f"   Basics keys: {list(profile.get('basics', {}).keys())}")

        if base:
            click.echo(click.style("\n📊 Base template structure:", fg="cyan"))
            click.echo("   Keys: {list(base.keys())}")
            if "sections" in base:
                click.echo("   Section columns:")
                for section_name, section_data in base.get("sections", {}).items():
                    cols = section_data.get("columns", "not set")
                    click.echo(f"     - {section_name}: {cols}")

        raise ValueError(f"Resume data validation failed: {e}") from e


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

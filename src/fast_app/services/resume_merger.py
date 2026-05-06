"""Resume merge service."""

import copy
from typing import Any

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
        logger.error(f"Generated data keys: {list(generated.keys())}")
        logger.error(f"Generated summary: {generated.get('summary', {})}")
        logger.error(f"Generated sections: {list(generated.get('sections', {}).keys())}")
        logger.error(f"Profile basics keys: {list(profile.get('basics', {}).keys())}")

        if base:
            logger.error(f"Base template keys: {list(base.keys())}")
            if "sections" in base:
                for section_name, section_data in base.get("sections", {}).items():
                    cols = section_data.get("columns", "not set")
                    logger.error(f"  Base section {section_name} columns: {cols}")

        raise ValueError(f"Resume data validation failed: {e}") from e

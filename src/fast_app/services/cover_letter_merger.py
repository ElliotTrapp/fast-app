"""Cover letter merge service."""

import copy
import uuid
from typing import Any

from ..log import logger
from ..models import CoverLetterData


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
        ValueError: If content is missing, empty, or validation fails
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
        result = {
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
    else:
        result = copy.deepcopy(base)

        # Populate basics from profile
        result["basics"] = profile.get("basics", {})

        # Preserve all sections from base (they're styling/layout for cover letters)
        # No need to override with generated content

        # Find and update the Cover Letter custom section
        custom_functions = result.get("customSections", [])
        cover_letter_section_idx = None

        for idx, section in enumerate(custom_functions):
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

    # Validate the structure matches CoverLetterData schema
    try:
        validated = CoverLetterData.model_validate(result)
        logger.success("Cover letter data validated successfully")
        return validated.model_dump()
    except Exception as e:
        logger.error(f"Cover letter data validation failed: {e}")
        logger.error(f"Recipient length: {len(recipient)}")
        logger.error(f"Content length: {len(cover_letter_content)}")
        logger.error(f"Profile basics keys: {list(profile.get('basics', {}).keys())}")

        if base:
            logger.error(f"Base template keys: {list(base.keys())}")
            if "customSections" in base:
                logger.error(f"Base custom sections count: {len(base.get('customSections', []))}")

        logger.error(f"Merged result keys: {list(result.keys())}")
        logger.error(f"Has basics: {'basics' in result}")
        logger.error(f"Has customSections: {'customSections' in result}")

        raise ValueError(f"Cover letter data validation failed: {e}") from e

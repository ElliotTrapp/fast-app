"""Text processing utilities for LLM response cleanup and string sanitization."""

import re


def sanitize_name(name: str) -> str:
    """Sanitize company or job title for use in paths.

    Removes commas, special characters, and extra spaces.

    Args:
        name: Raw name string

    Returns:
        Sanitized name safe for file paths
    """
    # Remove commas
    name = name.replace(",", "")
    # Remove special characters except spaces and hyphens
    name = "".join(c for c in name if c.isalnum() or c in " -")
    # Replace multiple spaces with single space
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def strip_markdown_json(content: str) -> str:
    """Strip markdown code blocks from LLM response if present.

    LLMs sometimes wrap JSON responses in markdown code blocks
    (e.g., ```json ... ```). This function removes those wrappers
    to get the raw JSON string.

    Args:
        content: Raw LLM response text, possibly wrapped in markdown.

    Returns:
        The content with markdown code block wrappers removed.
    """
    content = content.strip()
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    match = re.match(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content

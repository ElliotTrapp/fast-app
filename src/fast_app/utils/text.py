"""Text processing utilities for LLM response cleanup."""

import re


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

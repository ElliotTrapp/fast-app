"""Profile and file path utilities."""

import json
from pathlib import Path
from typing import Any


def find_profile_file(cli_path: str | None = None) -> Path:
    """Find profile file in order of precedence.

    Order:
    1. CLI --profile flag
    2. ./profile.json
    3. ../easy-apply/profile.json (sibling directory)

    Raises:
        FileNotFoundError: If profile file not found
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Profile file not found: {path}")

    cwd_path = Path.cwd() / "profile.json"
    if cwd_path.exists():
        return cwd_path

    sibling_path = Path.cwd().parent / "easy-apply" / "profile.json"
    if sibling_path.exists():
        return sibling_path

    raise FileNotFoundError(
        "No profile file found. Checked:\n"
        f"  1. --profile flag\n"
        f"  2. {cwd_path}\n"
        f"  3. {sibling_path}"
    )


def find_base_resume_file(cli_path: str | None = None) -> Path | None:
    """Find base resume template file.

    Order:
    1. CLI --base-resume flag
    2. ./base-resume.json
    3. None (returns None)

    Returns:
        Path to base resume file or None
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Base resume file not found: {path}")

    cwd_path = Path.cwd() / "base-resume.json"
    if cwd_path.exists():
        return cwd_path

    return None


def find_base_cover_letter_file(cli_path: str | None = None) -> Path | None:
    """Find base cover letter template file.

    Order:
    1. CLI --base-cover-letter flag
    2. ./base-cover-letter.json
    3. None (returns None)

    Returns:
        Path to base cover letter file or None
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Base cover letter file not found: {path}")

    cwd_path = Path.cwd() / "base-cover-letter.json"
    if cwd_path.exists():
        return cwd_path

    return None


def load_profile(cli_path: str | None = None) -> dict[str, Any]:
    """Load profile from file."""
    profile_path = find_profile_file(cli_path)
    return json.loads(profile_path.read_text())


def load_base_resume(cli_path: str | None = None) -> dict[str, Any] | None:
    """Load base resume template from file."""
    base_path = find_base_resume_file(cli_path)
    if base_path:
        return json.loads(base_path.read_text())
    return None


def load_base_cover_letter(cli_path: str | None = None) -> dict[str, Any] | None:
    """Load base cover letter template from file."""
    base_path = find_base_cover_letter_file(cli_path)
    if base_path:
        return json.loads(base_path.read_text())
    return None

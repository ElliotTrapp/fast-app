"""Utility modules for fast-app."""

from .async_helpers import run_async
from .cover_letter import (
    check_existing_cover_letter,
    merge_cover_letter_with_base,
)
from .interactive import ask_questions_interactive
from .profile import (
    find_base_cover_letter_file,
    find_base_resume_file,
    find_profile_file,
    load_base_cover_letter,
    load_base_resume,
    load_profile,
    sanitize_name,
)
from .resume import (
    check_existing_resume,
    merge_resume_with_base,
)
from .spinner import SpinnerContextManager
from .text import strip_markdown_json

__all__ = [
    "sanitize_name",
    "find_profile_file",
    "find_base_resume_file",
    "find_base_cover_letter_file",
    "load_profile",
    "load_base_resume",
    "load_base_cover_letter",
    "merge_resume_with_base",
    "merge_cover_letter_with_base",
    "check_existing_resume",
    "check_existing_cover_letter",
    "ask_questions_interactive",
    "run_async",
    "SpinnerContextManager",
    "strip_markdown_json",
]

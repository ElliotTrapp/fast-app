"""Services for fast-app."""

from .auth import (
    ALGORITHM,
    JWT_SECRET,
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    is_auth_enabled,
    verify_password,
)
from .cache import CacheManager, generate_job_id
from .cover_letter_merger import merge_cover_letter_with_base
from .fact_extractor import FactExtractor
from .job_extractor import JobExtractor
from .jsearch_service import JSearchService
from .knowledge import KnowledgeService
from .llm_service import LLMService
from .ollama import OllamaService
from .profile_service import ProfileService
from .reactive_resume import ReactiveResumeClient
from .resume_merger import merge_resume_with_base

__all__ = [
    "ALGORITHM",
    "CacheManager",
    "FactExtractor",
    "JSearchService",
    "JWT_SECRET",
    "JobExtractor",
    "KnowledgeService",
    "LLMService",
    "OllamaService",
    "ProfileService",
    "ReactiveResumeClient",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "generate_job_id",
    "hash_password",
    "is_auth_enabled",
    "merge_cover_letter_with_base",
    "merge_resume_with_base",
    "verify_password",
]

"""Data models for knowledge base."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Fact(BaseModel):
    """Atomic piece of knowledge extracted from Q&A."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    type: Literal["skill", "experience", "achievement", "preference", "general"]
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.now)
    last_confirmed: datetime = Field(default_factory=datetime.now)
    source: Literal["qa", "profile", "imported", "inferred"] = "qa"
    version: int = Field(default=1)
    supersedes: str | None = None
    job_url: str | None = None
    question: str | None = None
    metadata: dict | None = None


class Generation(BaseModel):
    """A resume/cover letter generation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    job_url: str
    job_title: str | None = None
    company: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    rating: int | None = Field(default=None, ge=1, le=5)
    feedback: str | None = None
    outcome: Literal["success", "failure", "pending"] | None = None


class Pattern(BaseModel):
    """Success or failure pattern extracted from generation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    generation_id: str | None = None
    pattern_type: Literal["success", "failure"]
    pattern_text: str
    keywords: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class KnowledgeContext(BaseModel):
    """Context built for LLM prompts."""

    relevant_facts: list[Fact] = Field(default_factory=list)
    stale_items: list[dict] = Field(default_factory=list)
    success_patterns: list[Pattern] = Field(default_factory=list)
    failure_patterns: list[Pattern] = Field(default_factory=list)
    current_profile: dict = Field(default_factory=dict)

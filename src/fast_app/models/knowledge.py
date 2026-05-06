"""Knowledge Pydantic models for fact extraction and semantic search.

This module defines the data models used by the knowledge pipeline:
fact extraction, storage, and retrieval.

## Models

- **ExtractedFact**: A single atomic fact extracted from Q&A
- **FactExtractionResult**: The result of extracting facts from a Q&A session
- **KnowledgeQuery**: A semantic search query
- **KnowledgeSearchResult**: A fact retrieved from the knowledge base

These models are used throughout the knowledge pipeline:

    Q&A → FactExtractor → ExtractedFact[] → KnowledgeService.store_facts()
                                            ↓
    Job → KnowledgeService.query_facts() → KnowledgeSearchResult[]
                                            ↓
    Question prompt (knowledge context injection)

See: docs/adr/006-knowledge-extraction-llm.md, docs/adr/002-chromadb-vector-memory.md
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ExtractedFact(BaseModel):
    """A single atomic fact extracted from a Q&A pair.

    Facts are the fundamental unit of knowledge in Fast-App. Each fact
    represents one discrete piece of information about the user, suitable
    for embedding in a vector database.

    Attributes:
        content: The fact itself (e.g., "5 years Python experience")
        category: Category for filtering (skill, experience, education, etc.)
        confidence: How clearly the fact was stated (0.0-1.0)
        source_question: The interview question that elicited this fact
        source_answer: The relevant portion of the user's answer
    """

    content: str = Field(
        ...,
        description="The atomic fact (e.g., '5 years Python experience')",
    )
    category: str = Field(
        ...,
        description=(
            "Category: skill, experience, education, certification, preference, personality, goal"
        ),
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How clearly the fact was stated (0.0-1.0)",
    )
    source_question: str = Field(
        ...,
        description="The interview question that elicited this fact",
    )
    source_answer: str = Field(
        ...,
        description="The relevant portion of the user's answer",
    )


class FactExtractionResult(BaseModel):
    """Result of extracting facts from Q&A pairs.

    This is the structured output of the LLM fact extraction chain.
    It contains a list of extracted facts and a brief summary of what
    was learned.

    Attributes:
        facts: List of extracted atomic facts
        summary: Brief summary of what was learned (1-2 sentences)
    """

    facts: list[ExtractedFact] = Field(
        default_factory=list,
        description="List of extracted atomic facts",
    )
    summary: str = Field(
        default="",
        description="Brief summary of what was learned (1-2 sentences)",
    )


class KnowledgeQuery(BaseModel):
    """A semantic search query for the knowledge base.

    Attributes:
        query: Natural language search string
        n: Number of results to return (default 5)
        category: Optional category filter (skill, experience, etc.)
    """

    query: str = Field(..., description="Natural language search string")
    n: int = Field(default=5, ge=1, le=50, description="Number of results")
    category: str | None = Field(
        default=None,
        description="Optional category filter",
    )


class FactCreate(BaseModel):
    """Schema for creating a new fact manually.

    Attributes:
        content: The fact content (e.g., "5 years Python experience").
        category: Category for filtering (skill, experience, education, etc.).
        source: Where this fact came from (e.g., "manual_entry").
        job_url: Optional URL of the job posting related to this fact.
        confidence: How clearly the fact was stated (0.0-1.0).
    """

    content: str = Field(..., description="The fact content")
    category: str = Field(default="general", description="Category for filtering")
    source: str | None = Field(default=None, description="Source of the fact")
    job_url: str | None = Field(default=None, description="Related job URL")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")


class FactUpdate(BaseModel):
    """Schema for updating an existing fact.

    All fields are optional — only provided fields will be updated.

    Attributes:
        content: Updated fact content.
        category: Updated category.
        source: Updated source.
        confidence: Updated confidence score.
    """

    content: str | None = Field(default=None, description="Updated fact content")
    category: str | None = Field(default=None, description="Updated category")
    source: str | None = Field(default=None, description="Updated source")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Updated confidence score"
    )


class KnowledgeSearchResult(BaseModel):
    """A fact retrieved from the knowledge base via semantic search.

    Attributes:
        id: ChromaDB document ID (UUID string) — use for deletion
        content: The fact content
        category: Category for filtering
        confidence: Extraction confidence score
        source: Where this fact came from (qa_session, manual_entry)
        distance: Semantic distance from the query (lower = more relevant)
        metadata: Full ChromaDB metadata dictionary
    """

    id: str = Field(default="", description="ChromaDB document ID (use for deletion)")
    content: str = Field(..., description="The fact content")
    category: str = Field(default="", description="Category (skill, experience, etc.)")
    confidence: float = Field(default=0.0, description="Extraction confidence (0.0-1.0)")
    source: str = Field(default="", description="Source of the fact")
    distance: float | None = Field(default=None, description="Semantic distance from query")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Full metadata")

"""Fact extraction service for distilling Q&A pairs into atomic facts.

This module provides the FactExtractor class, which uses a LangChain chain to
distill raw Q&A answers into discrete, atomic facts suitable for embedding and
storage in the vector database.

## Why Fact Extraction?

Raw Q&A answers are verbose and conflated:

    "Well, I've been coding for about 5 years, mostly in Python,
     and I led a small team at my last company."

This becomes 3 atomic facts:
    1. "5 years coding experience" (skill, confidence: 0.95)
    2. "Primary language is Python" (skill, confidence: 0.9)
    3. "Led a small team at previous company" (experience, confidence: 0.85)

Atomic facts are better for:
- **Embedding**: Each fact gets its own vector, improving retrieval precision
- **Deduplication**: Facts can be compared to avoid storing duplicates
- **Category filtering**: Metadata enables targeted retrieval (e.g., "skills only")
- **Gap analysis**: The question generator can identify what's NOT known

## Extraction Modes

1. **Auto-extract** (default): Facts are extracted and stored automatically
   after each Q&A session. No user intervention required.

2. **Review mode** (--review-facts flag): Facts are extracted but flagged for
   user review before storage. The user can accept, reject, or edit each fact.

## Pipeline Integration

    Q&A pairs → FactExtractor → KnowledgeService.store_facts() → ChromaDB

The FactExtractor is called after Q&A completion and before the next question
generation cycle, enabling knowledge-informed prompts in future sessions.

See: docs/adr/006-knowledge-extraction-llm.md, docs/guide/knowledge.md
"""

from __future__ import annotations

import json
from typing import Any

from ..log import logger
from ..models.knowledge import FactExtractionResult


class FactExtractor:
    """Extracts atomic facts from Q&A pairs using LLM distillation.

    This class wraps a LangChain chain that takes raw Q&A pairs and produces
    a structured FactExtractionResult containing discrete facts with metadata
    (category, confidence, source attribution).

    Attributes:
        llm_service: The LLMService instance for making LLM calls.
    """

    def __init__(self, llm_service: Any):
        """Initialize the fact extractor.

        Args:
            llm_service: An LLMService instance for making LLM calls.
        """
        self.llm_service = llm_service

    def extract_facts_from_answers(
        self,
        questions: list[str],
        answers: list[str],
        profile_data: dict[str, Any] | None = None,
        job_data: dict[str, Any] | None = None,
    ) -> FactExtractionResult:
        """Extract atomic facts from Q&A pairs.

        Takes the raw questions and answers from an interview session, along with
        optional profile and job context, and distills them into discrete facts
        suitable for embedding and storage.

        Args:
            questions: List of question strings.
            answers: List of answer strings (must be same length as questions).
            profile_data: Optional user profile for deduplication (facts already
                in the profile won't be duplicated).
            job_data: Optional job context for relevance filtering.

        Returns:
            FactExtractionResult containing extracted facts and a summary.

        Note:
            This method makes one LLM call per extraction. The cost is
            approximately 500 tokens per extraction (~1 cent with typical models).
        """
        qa_pairs = "\n".join(f"Q: {q}\nA: {a}" for q, a in zip(questions, answers))

        logger.llm_call(
            "extract_facts",
            {"qa_count": len(questions)},
        )

        result = self.llm_service.generate_with_schema(
            prompt=self._build_prompt(qa_pairs, profile_data, job_data),
            schema=FactExtractionResult,
        )

        logger.llm_result(
            "fact_extraction",
            {"fact_count": len(result.facts)},
        )

        return result

    def _build_prompt(
        self,
        qa_pairs: str,
        profile_data: dict[str, Any] | None,
        job_data: dict[str, Any] | None,
    ) -> str:
        """Build the fact extraction prompt.

        Args:
            qa_pairs: Formatted Q&A pairs string.
            profile_data: Optional profile for deduplication.
            job_data: Optional job context.

        Returns:
            The complete prompt string for the LLM.
        """
        from ..prompts.fact_extraction import get_fact_extraction_prompt

        return get_fact_extraction_prompt(
            qa_pairs=qa_pairs,
            profile_data=json.dumps(profile_data or {}),
            job_data=json.dumps(job_data or {}),
        )

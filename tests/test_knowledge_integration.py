"""Tests for knowledge base integration."""

import tempfile
from pathlib import Path
import pytest
from fast_app.knowledge import KnowledgeBase
from fast_app.knowledge.integration import (
    extract_facts_from_qa,
    get_relevant_context,
    record_generation,
    summarize_knowledge_base,
    format_context_for_prompt,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    kb = KnowledgeBase(str(db_path))

    # Add some test facts
    kb.add_fact("I know Python very well", fact_type="skill", source="qa")
    kb.add_fact("I worked at Google for 5 years", fact_type="experience", source="qa")
    kb.add_fact("I prefer remote work", fact_type="preference", source="qa")

    yield kb

    # Clean up
    if db_path.exists():
        db_path.unlink()


def test_extract_facts_from_qa():
    """Test extracting facts from Q&A."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        kb = KnowledgeBase(str(db_path))

        questions = [
            {"id": "q1", "text": "What skills do you have?"},
            {"id": "q2", "text": "Where have you worked?"},
            {"id": "q3", "text": "What achievements are you proud of?"},
        ]

        answers = [
            {"question_id": "q1", "answer": "Python, JavaScript, and SQL"},
            {"question_id": "q2", "answer": "Google and Microsoft"},
            {"question_id": "q3", "answer": "Led a team of 10 engineers"},
        ]

        fact_ids = extract_facts_from_qa(questions, answers, kb, debug=False)

        assert len(fact_ids) == 3
        assert kb.get_stats()["total_facts"] == 3

        # Check fact types are inferred correctly
        facts = kb.search_facts(limit=10)
        fact_types = {f["type"] for f in facts}
        assert "skill" in fact_types or "experience" in fact_types

    finally:
        if db_path.exists():
            db_path.unlink()


def test_extract_facts_skips_empty_answers():
    """Test that empty answers are skipped."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        kb = KnowledgeBase(str(db_path))

        questions = [
            {"id": "q1", "text": "What skills do you have?"},
            {"id": "q2", "text": "Where have you worked?"},
        ]

        answers = [
            {"question_id": "q1", "answer": "Python"},
            {"question_id": "q2", "answer": ""},  # Empty
        ]

        fact_ids = extract_facts_from_qa(questions, answers, kb, debug=False)

        assert len(fact_ids) == 1

    finally:
        if db_path.exists():
            db_path.unlink()


def test_get_relevant_context(temp_db):
    """Test getting relevant context for a job."""
    job_data = {
        "title": "Senior Python Developer",
        "company": "TechCorp",
        "description": "Looking for a Python developer with leadership experience",
    }

    context = get_relevant_context(temp_db, job_data, debug=False)

    # Should find the Python skill fact
    assert len(context) > 0
    assert any("Python" in item["fact"]["text"] for item in context)


def test_get_relevant_context_filters_low_confidence():
    """Test that low-confidence facts are filtered out."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        kb = KnowledgeBase(str(db_path))

        # Add fact with low confidence
        kb.add_fact("I like golf", fact_type="preference", confidence=0.3, source="qa")
        kb.add_fact("I know Python", fact_type="skill", confidence=0.9, source="qa")

        job_data = {
            "title": "Developer",
            "company": "TechCorp",
            "description": "Python developer",
        }

        context = get_relevant_context(kb, job_data, debug=False)

        # Low confidence fact should not appear
        assert all("golf" not in item["fact"]["text"] for item in context)

    finally:
        if db_path.exists():
            db_path.unlink()


def test_record_generation():
    """Test recording a generation event."""
    db_path = Path(tempfile.mktemp(suffix=".db"))
    try:
        kb = KnowledgeBase(str(db_path))

        # Add some facts
        fact_id1 = kb.add_fact("Fact 1", fact_type="skill", source="qa")
        fact_id2 = kb.add_fact("Fact 2", fact_type="experience", source="qa")

        # Record generation
        gen_id = record_generation(
            kb=kb,
            job_url="https://example.com/job/123",
            job_title="Senior Developer",
            company="TechCorp",
            related_facts=[fact_id1, fact_id2],
            debug=False,
        )

        assert gen_id is not None

        # Check generation was recorded
        gen = kb.get_generation(gen_id)
        assert gen is not None
        assert gen["job_title"] == "Senior Developer"
        assert gen["company"] == "TechCorp"

    finally:
        if db_path.exists():
            db_path.unlink()


def test_summarize_knowledge_base(temp_db):
    """Test knowledge base summary."""
    summary = summarize_knowledge_base(temp_db)

    assert summary["total_facts"] == 3
    assert "skill" in summary["by_type"]
    assert "experience" in summary["by_type"]
    assert "preference" in summary["by_type"]
    assert summary["by_source"]["qa"] == 3
    assert summary["total_generations"] == 0
    assert 0.0 <= summary["health_score"] <= 1.0


def test_format_context_for_prompt():
    """Test formatting context for LLM prompt."""
    context = [
        {
            "fact": {"id": "1", "text": "I know Python", "type": "skill"},
            "confidence": 0.9,
            "relevance": 0.8,
        },
        {
            "fact": {"id": "2", "text": "I worked at Google", "type": "experience"},
            "confidence": 0.85,
            "relevance": 0.6,
        },
    ]

    formatted = format_context_for_prompt(context)

    assert "## Knowledge Base Context" in formatted
    assert "I know Python" in formatted
    assert "I worked at Google" in formatted
    assert "### Skills" in formatted
    assert "### Experiences" in formatted
    assert "confidence:" in formatted


def test_format_context_handles_empty():
    """Test formatting empty context."""
    formatted = format_context_for_prompt([])

    assert formatted == ""

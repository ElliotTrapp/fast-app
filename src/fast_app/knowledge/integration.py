"""Integration between knowledge base and resume generation."""

from datetime import datetime
from pathlib import Path
from typing import Any

from .kb import KnowledgeBase


def extract_facts_from_qa(
    questions: list[dict], answers: list[dict], kb: KnowledgeBase, debug: bool = False
) -> list[str]:
    """Extract facts from Q&A session and store in knowledge base.

    Args:
        questions: List of question dicts with 'id' and 'text'
        answers: List of answer dicts with 'question_id' and 'answer'
        kb: KnowledgeBase instance
        debug: Enable debug output

    Returns:
        List of fact IDs that were added
    """
    if debug:
        print("\n📚 Extracting facts from Q&A...")

    fact_ids = []

    # Map question IDs to text
    q_map = {q["id"]: q["text"] for q in questions}

    for answer in answers:
        q_id = answer.get("question_id")
        q_text = q_map.get(q_id, "Unknown question")
        a_text = answer.get("answer", "")

        if not a_text or a_text.strip().lower() in ["n/a", "none", "skip", ""]:
            if debug:
                print(f"  ⏭️  Skipping empty answer for: {q_text[:50]}...")
            continue

        # Create fact from Q&A
        # Format: "Q: [question] A: [answer]"
        fact_text = f"Q: {q_text} A: {a_text}"

        # Determine fact type based on keywords in question
        fact_type = _infer_fact_type(q_text, a_text)

        if debug:
            print(f"  ✅ Adding fact ({fact_type}): {fact_text[:80]}...")

        fact_id = kb.add_fact(
            text=fact_text,
            fact_type=fact_type,
            source="qa",
            confidence=0.9,  # High confidence for user-provided answers
        )
        fact_ids.append(fact_id)

    if debug:
        stats = kb.get_stats()
        print(f"\n📊 Knowledge base now has {stats['total_facts']} facts")

    return fact_ids


def _infer_fact_type(question: str, answer: str) -> str:
    """Infer the fact type from question and answer content.

    Args:
        question: The question text
        answer: The answer text

    Returns:
        Fact type: skill, experience, achievement, preference, or general
    """
    q_lower = question.lower()
    a_lower = answer.lower()

    # Skill-related keywords
    if any(
        kw in q_lower or kw in a_lower
        for kw in ["skill", "technology", "language", "framework", "tool"]
    ):
        return "skill"

    # Experience-related keywords
    if any(
        kw in q_lower or kw in a_lower
        for kw in ["experience", "worked", "job", "company", "year", "role"]
    ):
        return "experience"

    # Achievement-related keywords
    if any(
        kw in q_lower or kw in a_lower
        for kw in ["achieved", "accomplished", "success", "award", "result"]
    ):
        return "achievement"

    # Preference-related keywords
    if any(kw in q_lower or kw in a_lower for kw in ["prefer", "like", "want", "avoid", "focus"]):
        return "preference"

    return "general"


def get_relevant_context(
    kb: KnowledgeBase, job_data: dict[str, Any], debug: bool = False
) -> list[dict]:
    """Get relevant facts from knowledge base for job.

    Args:
        kb: KnowledgeBase instance
        job_data: Job data dict with title, company, description
        debug: Enable debug output

    Returns:
        List of relevant facts with their current confidence
    """
    if debug:
        print("\n🔍 Searching knowledge base for relevant facts...")

    # Get all facts with confidence above threshold
    all_facts = kb.search_facts(limit=1000)

    # Build context from facts
    context = []

    # Filter facts by relevance to job
    job_title = job_data.get("title", "").lower()
    job_company = job_data.get("company", "").lower()
    job_desc = job_data.get("description", "").lower()

    # Keywords from job posting
    job_keywords = set(job_desc.split()) | set(job_title.split()) | set(job_company.split())

    for fact in all_facts:
        # Get current confidence (decayed from initial)
        current_conf = kb.get_current_confidence(fact["id"])

        # Skip low-confidence facts
        if current_conf < 0.5:
            if debug:
                print(
                    f"  ⏭️  Skipping low-confidence fact: {fact['text'][:40]}... ({current_conf:.0%})"
                )
            continue

        # Check relevance (fact text overlaps with job)
        fact_words = set(fact["text"].lower().split())
        relevance = len(fact_words & job_keywords) / max(len(fact_words), 1)

        # Boost skill and experience facts
        if fact["type"] in ("skill", "experience"):
            relevance += 0.2

        # Add to context if relevant enough
        if relevance > 0.1 or fact["type"] in ("skill", "experience", "achievement"):
            context.append(
                {
                    "fact": fact,
                    "confidence": current_conf,
                    "relevance": min(1.0, relevance),
                }
            )

            if debug:
                print(
                    f"  ✅ {fact['type']}: {fact['text'][:60]}... (conf: {current_conf:.0%}, rel: {relevance:.0%})"
                )

    if debug:
        print(f"\n📊 Found {len(context)} relevant facts for this job")

    return context


def record_generation(
    kb: KnowledgeBase,
    job_url: str,
    job_title: str,
    company: str,
    related_facts: list[str] | None = None,
    debug: bool = False,
) -> str:
    """Record a generation event in the knowledge base.

    Args:
        kb: KnowledgeBase instance
        job_url: URL of the job posting
        job_title: Title of the job
        company: Company name
        related_facts: List of fact IDs used in this generation
        debug: Enable debug output

    Returns:
        Generation ID
    """
    if debug:
        print(f"\n📝 Recording generation: {job_title} at {company}")

    gen_id = kb.record_generation(
        job_url=job_url,
        job_title=job_title,
        company=company,
        facts_used=related_facts,  # Pass as facts_used parameter
    )

    if related_facts and debug:
        print(f"  ✅ Linked {len(related_facts)} facts to generation")

    return gen_id


def record_feedback(
    kb: KnowledgeBase,
    generation_id: str,
    rating: int,
    feedback: str | None = None,
    facts_confirmed: list[str] | None = None,
    debug: bool = False,
) -> None:
    """Record feedback for a generation.

    Args:
        kb: KnowledgeBase instance
        generation_id: ID of the generation
        rating: Rating 1-5 (5 is best)
        feedback: Optional feedback text
        facts_confirmed: List of fact IDs that were confirmed accurate
        debug: Enable debug output
    """
    if debug:
        print(f"\n💬 Recording feedback for generation {generation_id[:8]}...")

    kb.record_feedback(
        generation_id=generation_id,
        rating=rating,
        feedback=feedback,
    )

    # Refresh confirmed facts (boosts their confidence)
    if facts_confirmed:
        for fact_id in facts_confirmed:
            kb.refresh_fact(fact_id, confirmed=True)

        if debug:
            print(f"  ✅ Confirmed {len(facts_confirmed)} facts")

    if debug:
        outcome = "success" if rating >= 3 else "failure"
        print(f"  📊 Generation marked as: {outcome}")


def format_context_for_prompt(context: list[dict]) -> str:
    """Format knowledge base context for LLM prompt.

    Args:
        context: List of context dicts from get_relevant_context()

    Returns:
        Formatted string for prompt
    """
    if not context:
        return ""

    lines = ["\n## Knowledge Base Context\n"]
    lines.append("The following facts from the user's profile may be relevant:\n")

    # Group by type
    by_type: dict[str, list] = {
        "skill": [],
        "experience": [],
        "achievement": [],
        "preference": [],
        "general": [],
    }

    for item in context:
        fact = item["fact"]
        conf = item["confidence"]
        by_type[fact["type"]].append(f"- {fact['text']} (confidence: {conf:.0%})")

    # Add each section
    for fact_type, facts in by_type.items():
        if facts:
            lines.append(f"\n### {fact_type.title()}s")
            lines.extend(facts)

    return "\n".join(lines)


def summarize_knowledge_base(kb: KnowledgeBase) -> dict[str, Any]:
    """Get a summary of the knowledge base state.

    Args:
        kb: KnowledgeBase instance

    Returns:
        Summary dict with counts and health metrics
    """
    stats = kb.get_stats()

    # Calculate health metrics
    total_facts = stats["total_facts"]
    facts_needing_refresh = stats["facts_needing_refresh"]
    avg_confidence = stats.get("avg_confidence", 0.0)

    health_score = 1.0
    if total_facts > 0:
        health_score = 1.0 - (facts_needing_refresh / total_facts)
        health_score *= avg_confidence / 0.8  # Boost if high confidence

    return {
        "total_facts": total_facts,
        "by_type": stats.get("facts_by_type", {}),
        "by_source": stats.get("facts_by_source", {}),
        "needing_refresh": facts_needing_refresh,
        "average_confidence": avg_confidence,
        "health_score": min(1.0, health_score),
        "total_generations": stats.get("total_generations", 0),
        "successful_generations": stats.get("successful_generations", 0),
    }

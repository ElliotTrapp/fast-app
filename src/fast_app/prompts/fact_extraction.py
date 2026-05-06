# ruff: noqa: E501
"""Fact extraction prompt template.

This module provides the prompt template for LLM-based fact extraction.
The prompt is carefully designed to produce structured, atomic output
from raw Q&A pairs.

See: docs/adr/006-knowledge-extraction-llm.md
"""

FACT_EXTRACTION_PROMPT = """You are a knowledge extraction specialist. Your task is to distill
discrete, atomic facts from interview Q&A pairs.

## Rules
1. Each fact must be a single, self-contained statement
2. Each fact must be specific (not vague like "has experience")
3. Categorize each fact into one of: skill, experience, education, certification,
   preference, personality, goal
4. Assign a confidence score (0.0-1.0) based on how clearly the fact was stated
5. Do not infer facts that aren't supported by the answer
6. Do not duplicate facts already in the known profile

## Known Profile
{profile_data}

## Job Context
{job_data}

## Q&A Pairs
{qa_pairs}

## Output Format
Return a JSON object with:
- "facts": array of objects, each with: content, category, confidence,
  source_question, source_answer
- "summary": brief summary of what was learned (1-2 sentences)

Example output:
{{
    "facts": [
        {{
            "content": "5 years Python experience",
            "category": "skill",
            "confidence": 0.95,
            "source_question": "How many years of Python experience do you have?",
            "source_answer": "About 5 years"
        }},
        {{
            "content": "Led team of 8 engineers at Acme Corp",
            "category": "experience",
            "confidence": 0.9,
            "source_question": "Have you managed teams?",
            "source_answer": "Yes, I led a team of 8 at my last company"
        }}
    ],
    "summary": "Candidate has 5 years of Python experience and team leadership background."
}}"""


def get_fact_extraction_prompt(
    qa_pairs: str,
    profile_data: str = "{}",
    job_data: str = "{}",
) -> str:
    """Generate the fact extraction prompt with filled variables.

    Args:
        qa_pairs: Formatted Q&A pairs string.
        profile_data: JSON string of the user's known profile.
        job_data: JSON string of the job data.

    Returns:
        Complete prompt string for the LLM.
    """
    return FACT_EXTRACTION_PROMPT.format(
        qa_pairs=qa_pairs,
        profile_data=profile_data,
        job_data=job_data,
    )


PROFILE_FACT_EXTRACTION_PROMPT = """You are a knowledge extraction specialist. Your task is to distill
discrete, atomic facts from a user profile.

## Rules
1. Each fact must be a single, self-contained statement
2. Each fact must be specific (not vague like "has experience")
3. Categorize each fact into one of: skill, experience, education, certification,
   preference, personality, goal
4. Assign a confidence score (0.0-1.0) based on how clearly the fact is stated
5. Extract facts from ALL sections of the profile (skills, work history, education, summary, etc.)
6. For work experience, extract individual skills and accomplishments, not just job titles

## Profile Data
{profile_data}

## Output Format
Return a JSON object with:
- "facts": array of objects, each with: content, category, confidence,
  source_question, source_answer
- "summary": brief summary of what was learned (1-2 sentences)

For source_question, use "profile_import". For source_answer, quote the relevant
part of the profile data.

Example output:
{{
    "facts": [
        {{
            "content": "5 years Python experience",
            "category": "skill",
            "confidence": 0.95,
            "source_question": "profile_import",
            "source_answer": "Skills: Python (5 years)"
        }},
        {{
            "content": "Led team of 8 engineers at Acme Corp",
            "category": "experience",
            "confidence": 0.9,
            "source_question": "profile_import",
            "source_answer": "Senior Engineer at Acme Corp - managed team of 8"
        }}
    ],
    "summary": "Experienced Python developer with team leadership background."
}}"""


def get_profile_fact_extraction_prompt(profile_data: str = "{}") -> str:
    """Generate the profile fact extraction prompt with filled variables.

    Args:
        profile_data: JSON string of the user's profile data.

    Returns:
        Complete prompt string for the LLM.
    """
    return PROFILE_FACT_EXTRACTION_PROMPT.format(profile_data=profile_data)

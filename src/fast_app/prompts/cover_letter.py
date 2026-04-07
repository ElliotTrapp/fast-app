"""Prompt templates for cover letter generation."""

from typing import Any

from ..models import CoverLetterContent


def get_cover_letter_prompt(
    job_data: dict[str, Any],
    profile_data: dict[str, Any],
    questions: list[str] | None = None,
    answers: list[str] | None = None,
) -> str:
    """Generate the prompt for cover letter writing.

    Args:
        job_data: Extracted job data
        profile_data: User profile data
        questions: Optional list of questions asked
        answers: Optional list of answers to questions

    Returns:
        Prompt string for LLM
    """
    questionnaire_section = ""
    if questions and answers:
        qanda = "\n".join(f"Q: {q}\nA: {a}" for q, a in zip(questions, answers) if a.strip())
        if qanda:
            questionnaire_section = f"""
## Candidate's Additional Context (from questionnaire)
{qanda}
"""

    candidate_name = profile_data.get("basics", {}).get("name", "the candidate")

    return f"""You are an expert cover letter writer. Write a compelling, professional cover letter.

## Job Details
- Title: {job_data.get("title", "Unknown")}
- Company: {job_data.get("company", "Unknown")}
- Location: {job_data.get("location", "Unknown")}
- Description:
{job_data.get("description", "No description available")}

## Required Skills (from job)
{job_data.get("skills", "Not specified")}

## Candidate Profile
{profile_data}
{questionnaire_section}
## WORD COUNT REQUIREMENT - CRITICAL
The cover letter MUST be 400-500 words in length. This is a hard requirement.

## CONTENT REQUIREMENTS - CRITICAL
The cover letter MUST address these THREE elements:
1. VALUE: Explain the value and impact you can bring to the organization
2. ORGANIZATION: Why you want to work for THIS specific organization
3. ROLE: Why you want THIS specific role and how it fits your career

Structure your cover letter with CLEAR BOLD section headers using <strong> tags.

## CRITICAL: EM DASHES ARE FORBIDDEN
You MUST NOT use em dashes (— or –) anywhere in the cover letter.
Use commas, semicolons, or periods instead.

## Instructions
1. Write a compelling professional cover letter (400-500 words)
2. Use BOLD section headers formatted as <strong>Header Name</strong>
3. Focus PRIMARILY on the VALUE you bring to the organization
4. Explain WHY you want to work for THIS organization specifically
5. Explain WHY you want THIS specific role
6. DO NOT simply repeat skills from the resume
7. Make the candidate stand out with SPECIFIC achievements and impacts
8. Use ACTIVE voice and STRONG verbs

## Formatting Requirements
- Use HTML formatting with <p> tags for each paragraph
- Use <strong>Section Headers</strong> for clear sections (e.g., Why I Want to Join)
- Each paragraph should be wrapped in <p>...</p> tags
- End with "Sincerely,</p><p>{candidate_name}</p>"
- NO EM DASHES anywhere in the text

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{CoverLetterContent.model_json_schema()}

Return valid JSON matching the CoverLetterContent schema exactly."""

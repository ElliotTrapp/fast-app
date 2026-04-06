"""Prompt templates for resume generation."""

import json
from typing import Dict, Any, List, Optional

from ..models import ResumeData


def get_resume_prompt(
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    questions: Optional[List[str]] = None,
    answers: Optional[List[str]] = None,
) -> str:
    """Generate the prompt for resume tailoring.

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

    return f"""You are an expert resume writer. Generate a tailored resume for this job using the candidate's profile.

## Job Details
- Title: {job_data.get("title", "Unknown")}
- Company: {job_data.get("company", "Unknown")}
- Location: {job_data.get("location", "Unknown")}
- Description:
{job_data.get("description", "No description available")}

## Required Skills (from job)
{job_data.get("skills", "Not specified")}

## Candidate Profile
{json.dumps(profile_data, indent=2)}
{questionnaire_section}
## Instructions
1. SELECT the most relevant work experiences from the profile that match this job
2. ORDER skills by relevance to the job requirements
3. TAILOR the summary to highlight fit for this specific role (3-4 sentences)
4. FORMAT descriptions as HTML bullet lists: <ul><li>...</li></ul>
5. For each skill group, include the name and keywords list
6. Generate UUIDs for all 'id' fields (use format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
7. Set all 'hidden' fields to false
8. DO NOT include any picture or photo references

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{ResumeData.model_json_schema()}

Return valid JSON matching the ResumeData schema exactly."""

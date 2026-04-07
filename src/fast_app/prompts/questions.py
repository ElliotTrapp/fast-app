"""Prompt templates for question generation."""

import json
from typing import Any

from ..models import QuestionContent


def get_questions_prompt(job_data: dict[str, Any], profile_data: dict[str, Any]) -> str:
    """Generate the prompt for asking clarifying questions.

    Args:
        job_data: Extracted job data
        profile_data: User profile data

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert career consultant preparing to write a compelling cover letter.

## Job Details
- Title: {job_data.get("title", "Unknown")}
- Company: {job_data.get("company", "Unknown")}
- Location: {job_data.get("location", "Unknown")}
- Description:
{job_data.get("description", "No description available")}

## Required Skills (from job)
{job_data.get("skills", "Not specified")}

## Candidate Profile Summary
{json.dumps(profile_data, indent=2)}

## Instructions
Based on the job requirements and candidate profile, generate up to 8 questions
to create the most compelling cover letter and tailored resume.

Focus PRIMARILY on cover letter creation. The questions should help gather
information to write a cover letter that:
1. Explains the VALUE the candidate can bring to this organization
2. Explains WHY the candidate wants to work for THIS company
3. Explains WHY the candidate wants THIS specific role
4. Highlights SPECIFIC achievements and impacts relevant to this role
5. Demonstrates knowledge of and enthusiasm for the company

Also ask about:
6. Relevant experiences for the resume (to select most impactful ones)
7. Quantifiable achievements and metrics that could be highlighted
8. Unique value propositions or differentiators for this role

Only ask questions where the answer would improve the cover letter quality.
Skip questions where the answer would be obvious from the profile or job.

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{QuestionContent.model_json_schema()}

Return valid JSON matching the QuestionData schema exactly."""


def get_questions_schema() -> dict:
    """Return the JSON schema for question responses."""
    return QuestionContent.model_json_schema()

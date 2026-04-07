"""Prompt templates for question generation."""

import json
from typing import Any

from ..models import QuestionData


def get_questions_prompt(job_data: dict[str, Any], profile_data: dict[str, Any]) -> str:
    """Generate the prompt for asking clarifying questions.

    Args:
        job_data: Extracted job data
        profile_data: User profile data

    Returns:
        Prompt string for LLM
    """
    return f"""You are an expert resume writer preparing to tailor a resume for a job application.

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
Based on the job requirements and candidate profile, generate up to 8 questions that would help create the strongest possible tailored resume and cover letter. 

Focus on:
1. Specific experiences related to key job requirements
2. Quantifiable achievements that could be highlighted
3. Relevant projects or work not in the profile
4. Technologies or skills mentioned in the job description
5. Company-specific knowledge or why they're interested in this role
6. Leadership, mentorship, or collaboration experiences
7. Unique value propositions or differentiators

Only ask questions that would meaningfully improve the resume quality. Skip questions where the answer would be obvious from the profile or job description.

## Critical Constraint
Return ONLY valid JSON matching this schema. No additional text outside the JSON.

## Schema Overview
{QuestionData.model_json_schema()}

Return valid JSON matching the QuestionData schema exactly."""


def get_questions_schema() -> dict:
    """Return the JSON schema for question responses."""
    return QuestionData.model_json_schema()

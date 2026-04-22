"""Prompt templates for resume generation."""

import json
from typing import Any

from ..models import ResumeContent


def get_resume_prompt(
    job_data: dict[str, Any],
    profile_data: dict[str, Any],
    questions: list[str] | None = None,
    answers: list[str] | None = None,
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

    return f"""You are an expert resume writer. Generate a FITTED one-page A4 resume
using the candidate's profile.

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
## PAGE LENGTH CONSTRAINT - CRITICAL
The resume MUST fit on a SINGLE A4 page when formatted. This means:
- KEEP summaries CONCISE (2-3 sentences maximum)
- INCLUDE ONLY the most RELEVANT experiences for this job (typically 3-4 max)
- EXCLUDE less relevant or older experiences
- Keep bullet points BRIEF and impactful (aim for 3-5 bullets per role)
- PRIORITIZE content by relevance to THIS specific job

## Experience Structure - CRITICAL
When the candidate has MULTIPLE POSITIONS at the SAME COMPANY (e.g., multiple roles at NASA JPL):
- Create ONE ExperienceItem per unique company
- Put ALL positions at that company into the 'roles' array
- Each RoleItem has: position, period, description (the bullet points for THAT role)
- DO NOT create separate ExperienceItems for each position at the same company

Example correct structure:
{{
  "company": "NASA Jet Propulsion Laboratory",
  "location": "Pasadena, CA",
  "roles": [
    {{
      "position": "Team Lead",
      "period": "Jan 2020 - June 2025",
      "description": "<ul><li>Bullet for Team Lead role only</li></ul>"
    }},
    {{
      "position": "Software Engineer",
      "period": "Jan 2018 - Dec 2019",
      "description": "<ul><li>Bullet for Software Engineer role only</li></ul>"
    }}
  ]
}}

## Instructions
1. SELECT ONLY the most RELEVANT experiences that match THIS job's requirements
2. GROUP positions at the same company into ONE ExperienceItem with multiple roles
3. ORDER skills by relevance to the job requirements
4. Write a TIGHT, FOCUSED summary (2-3 sentences max) highlighting fit for this role
5. FORMAT descriptions as HTML bullet lists: <ul><li>...</li></ul>
6. For each skill group, include the name and keywords list
7. Generate UUIDs for all 'id' fields (use format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
8. Set all 'hidden' fields to false
9. Preserve EXACT bullet points from profile for each role - do NOT mix bullets

## Critical Constraints
- Return ONLY valid JSON matching this schema
- The resume MUST be concise enough to fit ONE A4 page
- No additional text outside the JSON
- GROUP same-company positions into ONE ExperienceItem with multiple RoleItems

## Schema Overview
{ResumeContent.model_json_schema()}

Return valid JSON matching the ResumeContent schema exactly."""

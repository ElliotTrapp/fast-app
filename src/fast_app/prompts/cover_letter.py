"""Prompt templates for cover letter generation."""

from typing import Dict, Any, List, Optional


def get_cover_letter_prompt(
    job_data: Dict[str, Any],
    profile_data: Dict[str, Any],
    questions: Optional[List[str]] = None,
    answers: Optional[List[str]] = None,
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

    return f"""You are an expert cover letter writer. Write a compelling, professional, and personal cover letter for this job.

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
## Instructions
1. Write a professional, confident, and personal cover letter (under 350 words)
2. Make the candidate stand out as an outstanding candidate
3. DO NOT simply repeat skills already listed in the resume
4. Focus on unique value, achievements, and fit for this specific role
5. Be specific about why this company and role appeal to the candidate
6. Show genuine enthusiasm and knowledge about the company
7. Structure: Opening hook, 2-3 body paragraphs with section headers, brief closing, signature

## Formatting Requirements
- Use HTML formatting with <p> tags for each paragraph
- Use <strong>Section Headers</strong> for section headers (e.g., <strong>Why This Role Appeals to Me</strong>)
- Each paragraph should be wrapped in <p>...</p> tags
- End with "Sincerely,</p><p>{candidate_name}</p>"

## Output Format
Return a JSON object with two fields:
- "recipient": Opening line in HTML like "<p>Dear Company Team,</p>"
- "content": The full cover letter body in HTML format with <p> tags for paragraphs, <strong> tags for section headers, and proper signature

Example content structure:
"<p>Opening paragraph that hooks the reader...</p><p><strong>Why This Role Appeals to Me</strong></p><p>Explanation of why the role and company are appealing...</p><p><strong>Relevant Experience</strong></p><p>Highlighting specific achievements...</p><p><strong>What I Bring</strong></p><p>Key strengths and value...</p><p>Thank you for considering my application. I would welcome the opportunity to discuss how my experience could contribute to the team's mission.</p><p>Sincerely,</p><p>{candidate_name}</p>"

Return only valid JSON."""

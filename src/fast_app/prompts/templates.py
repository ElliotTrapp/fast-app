"""LangChain prompt templates for LLM generation.

This module provides ChatPromptTemplate instances for each generation task.
These templates replace the f-string based prompts in the prompts/ directory
when using LLMService. The templates use LangChain's prompt composition,
which enables:

1. Variable injection at runtime (job_data, profile_data, knowledge_context)
2. Structured output parsing via PydanticOutputParser or with_structured_output()
3. Chain composition with the | (pipe) operator
4. Easy prompt modification without code changes

## Template Structure

Each template follows the pattern:
    System message (role definition)
    + Human message (task + context variables)
    → LLM → Structured output parser

## Usage

    from fast_app.prompts.templates import get_questions_template
    from fast_app.models import QuestionContent

    template = get_questions_template()
    chain = template | llm | output_parser

    result = chain.invoke({
        "job_data": job_data,
        "profile_data": profile_data,
    })

## Knowledge Context (Phase 4)

Templates support an optional `knowledge_context` variable that injects
retrieved facts into the prompt. When knowledge is available, the prompt
includes a "What We Already Know" section that guides the LLM to ask about
gaps rather than known strengths.

See: docs/adr/001-llm-abstraction-langchain.md
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


def get_questions_template() -> ChatPromptTemplate:
    """Get the LangChain prompt template for question generation.

    This template replaces `prompts/questions.py` when using LLMService.
    It includes an optional knowledge_context variable for knowledge-informed
    question generation (Phase 4).

    Returns:
        ChatPromptTemplate with variables: job_data, profile_data, knowledge_section
    """
    template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert career advisor and interviewer. Your task is to "
                "generate clarifying questions that help tailor a resume and cover "
                "letter for a specific job application.",
            ),
            (
                "human",
                "## Job Information\n{job_data}\n\n"
                "## Candidate Profile\n{profile_data}\n\n"
                "{knowledge_section}"
                "\n\nGenerate 3-5 clarifying questions that will help create a "
                "tailored resume for this position. Focus on areas that need "
                "clarification or could significantly impact the resume content.",
            ),
        ]
    )
    return template.partial(knowledge_section="")


def get_questions_knowledge_section(knowledge_context: list[str] | None) -> str:
    """Generate the knowledge context section for question prompts.

    Args:
        knowledge_context: List of fact strings from the knowledge base.
            If None or empty, returns an empty string (no knowledge injection).

    Returns:
        Formatted knowledge section string, or empty string if no context.
    """
    if not knowledge_context:
        return ""

    facts = "\n".join(f"- {fact}" for fact in knowledge_context)
    return (
        "## What We Already Know About This Candidate\n"
        f"{facts}\n\n"
        "## INSTRUCTIONS\n"
        "Focus on areas NOT covered by the above knowledge. "
        "Ask about gaps between the job requirements and what we already know. "
        "Avoid asking about things we already have information on."
    )


def get_resume_template() -> ChatPromptTemplate:
    """Get the LangChain prompt template for resume generation.

    This template replaces `prompts/resume.py` when using LLMService.

    Returns:
        ChatPromptTemplate with variables: job_data, profile_data, questions, answers
    """
    template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert resume writer. Generate tailored resume content "
                "that matches the job requirements while accurately representing the "
                "candidate's experience. Output valid JSON matching the ResumeContent schema.",
            ),
            (
                "human",
                "## Job Information\n{job_data}\n\n"
                "## Candidate Profile\n{profile_data}\n\n"
                "## Questions and Answers\n{qa_section}\n\n"
                "Generate resume content (summary and sections) that highlights the "
                "candidate's relevant experience for this position.",
            ),
        ]
    )
    return template.partial(qa_section="No additional questions were asked.")


def get_resume_qa_section(questions: list[str], answers: list[str]) -> str:
    """Format Q&A pairs for the resume prompt.

    Args:
        questions: List of question strings.
        answers: List of answer strings.

    Returns:
        Formatted Q&A section string.
    """
    if not questions:
        return "No additional questions were asked."

    qa_lines = []
    for q, a in zip(questions, answers):
        qa_lines.append(f"Q: {q}\nA: {a}")
    return "\n\n".join(qa_lines)


def get_cover_letter_template() -> ChatPromptTemplate:
    """Get the LangChain prompt template for cover letter generation.

    This template replaces `prompts/cover_letter.py` when using LLMService.

    Returns:
        ChatPromptTemplate with variables: job_data, profile_data, questions, answers
    """
    template = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert cover letter writer. Generate a professional, "
                "tailored cover letter that matches the job requirements. "
                "Output valid JSON matching the CoverLetterContent schema.",
            ),
            (
                "human",
                "## Job Information\n{job_data}\n\n"
                "## Candidate Profile\n{profile_data}\n\n"
                "## Questions and Answers\n{qa_section}\n\n"
                "Generate a cover letter with a recipient and content that "
                "highlights the candidate's relevant experience for this position.",
            ),
        ]
    )
    return template.partial(qa_section="No additional questions were asked.")


def get_fact_extraction_template() -> ChatPromptTemplate:
    """Get the LangChain prompt template for fact extraction.

    This template distills raw Q&A pairs into atomic facts for storage in
    the knowledge base.

    Returns:
        ChatPromptTemplate with variables: qa_pairs, profile_data, job_data
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a knowledge extraction specialist. Your task is to distill "
                "discrete, atomic facts from interview Q&A pairs. Each fact must be "
                "a single, self-contained statement. Do not infer facts that aren't "
                "supported by the answers. Do not duplicate facts already in the "
                "known profile.",
            ),
            (
                "human",
                "## Known Profile\n{profile_data}\n\n"
                "## Job Context\n{job_data}\n\n"
                "## Q&A Pairs\n{qa_pairs}\n\n"
                "Extract all atomic facts from the Q&A pairs. For each fact, provide:\n"
                "- content: The fact itself (specific, self-contained statement)\n"
                "- category: One of: skill, experience, education, certification, "
                "preference, personality, goal\n"
                "- confidence: How clearly the fact was stated (0.0-1.0)\n"
                "- source_question: The question that elicited this fact\n"
                "- source_answer: The relevant portion of the answer\n\n"
                "Also provide a brief summary of what was learned.",
            ),
        ]
    )

"""Ollama service for resume generation.

Delegates generation methods to LLMService when LangChain is available,
falls back to direct Ollama SDK calls when it's not. Connection-related
methods (check_connection, check_model_available, ensure_model_available)
always use the direct Ollama SDK regardless of LangChain availability.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import requests
from ollama import Client

from ..config import Config, OllamaConfig
from ..log import logger
from ..models import CoverLetterContent, QuestionContent, ResumeContent
from ..prompts.cover_letter import get_cover_letter_prompt
from ..prompts.questions import get_questions_prompt
from ..prompts.resume import get_resume_prompt
from ..utils.async_helpers import run_async
from ..utils.retry import with_retry
from ..utils.spinner import SpinnerContextManager
from ..utils.text import strip_markdown_json


class OllamaService:
    """Service for interacting with Ollama for resume generation.

    Delegates generation methods to LLMService when LangChain is available,
    falls back to direct Ollama SDK calls when it's not.

    Args:
        config: OllamaConfig for direct SDK access, or full Config for
            LLMService delegation. When OllamaConfig is passed, a Config
            with default LLMConfig (provider="ollama") is constructed
            for LLMService if LangChain is available.
    """

    def __init__(self, config: OllamaConfig | Config):
        # Handle both OllamaConfig and Config for backward compatibility
        if isinstance(config, Config):
            self._full_config = config
            self.config = config.ollama
        else:
            self._full_config = None
            self.config = config

        headers = (
            {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else None
        )
        self.client = Client(host=self.config.endpoint, headers=headers)

        # Try to create LLMService for delegation when LangChain is available
        self._llm_service = None
        try:
            from .llm_service import LLMService

            if self._full_config is not None:
                self._llm_service = LLMService(self._full_config)
            else:
                # Construct a Config from OllamaConfig for LLMService.
                # LLMConfig defaults to provider="ollama" which uses ChatOllama
                # with the same endpoint and model from OllamaConfig.
                full_config = Config(ollama=self.config)
                self._llm_service = LLMService(full_config)
        except (ImportError, ValueError):
            # LangChain not installed or provider misconfigured —
            # fall back to direct Ollama SDK calls
            self._llm_service = None

    def check_connection(self) -> bool:
        """Check if Ollama endpoint is reachable."""
        try:
            logger.api_request("GET", f"{self.config.endpoint}/api/tags")
            self.client.list()
            logger.api_response(200)
            return True
        except requests.ConnectionError:
            logger.error(f"Cannot connect to Ollama at {self.config.endpoint}")
            return False
        except Exception as e:
            logger.error(f"Cannot connect to Ollama: {e}")
            return False

    def check_model_available(self) -> bool:
        """Check if the configured model is available."""
        try:
            logger.api_request("GET", f"{self.config.endpoint}/api/tags")
            models_response = self.client.list()
            models = models_response.get("models", [])
            model_names = [m.get("name", "") for m in models]

            for name in model_names:
                if self.config.model in name or name in self.config.model:
                    logger.api_response(200)
                    return True

            logger.api_response(200)
            logger.warning(f"Model '{self.config.model}' not found in available models")

            return False
        except Exception as e:
            logger.error(f"Error checking models: {e}")
            return False

    def get_connection_error_message(self, error: Exception) -> str:
        """Get actionable error message for connection failures.

        Args:
            error: The exception that occurred

        Returns:
            User-friendly error message with suggestions
        """
        error_str = str(error).lower()

        if "connection" in error_str or "refused" in error_str:
            return (
                f"Cannot connect to Ollama at {self.config.endpoint}\n"
                f"\n"
                f"  Suggestions:\n"
                f"  1. Ensure Ollama is running: ollama serve\n"
                f"  2. Check if endpoint is correct in config.json\n"
                f"  3. For Ollama Cloud, set 'cloud': true and provide 'api_key'"
            )

        if "timeout" in error_str:
            return (
                f"Ollama request timed out at {self.config.endpoint}\n"
                f"\n"
                f"  Suggestions:\n"
                f"  1. The model may be downloading - wait and try again\n"
                f"  2. GPU may be busy with another request\n"
                f"  3. Try a smaller model or increase timeout"
            )

        if "api" in error_str or "key" in error_str or "unauthorized" in error_str:
            return (
                "Ollama API authentication failed\n"
                "\n"
                "  Suggestions:\n"
                "  1. For Ollama Cloud, add 'api_key' to config.json\n"
                "  2. Get your API key from: https://ollama.ai/settings/keys\n"
                "  3. Ensure 'cloud': true in config.json"
            )

        return (
            f"Ollama error: {error}\n"
            f"\n"
            f"  Suggestions:\n"
            f"  1. Check Ollama status: ollama list\n"
            f"  2. Verify model is available: ollama pull {self.config.model}\n"
            f"  3. Check config.json for correct endpoint"
        )

    def ensure_model_available(self) -> bool:
        """Ensure the model is available, downloading if necessary."""
        if self.check_model_available():
            logger.llm_response(0, "Model already available")
            return True

        logger.warning(f"Model '{self.config.model}' not found. Downloading...")

        try:
            self.client.pull(self.config.model)
            logger.success(f"Model '{self.config.model}' downloaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to download model '{self.config.model}': {e}")
            return False

    async def _generate_questions_async(
        self, job_data: dict[str, Any], profile_data: dict[str, Any]
    ) -> list[str]:
        """Async version of question generation."""
        prompt = get_questions_prompt(job_data, profile_data)

        logger.header("Question Generation")
        logger.llm_request(self.config.endpoint, self.config.model, len(prompt))
        logger.llm_call(
            "generate_questions",
            {
                "job_title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
            },
        )

        response = await asyncio.to_thread(
            self.client.chat,
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            format=QuestionContent.model_json_schema(),
            think=False,
            options={"temperature": 0.3, "num_predict": 1000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        question_data = QuestionContent.model_validate_json(cleaned)
        questions = question_data.questions[:8]

        logger.llm_result("questions_parsed", {"count": len(questions)})
        for i, q in enumerate(questions, 1):
            logger.detail(f"Q{i}", q[:80] + "..." if len(q) > 80 else q)

        return questions

    @with_retry(max_retries=3, initial_delay=2.0)
    def generate_questions(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        knowledge_context: list[str] | None = None,
    ) -> list[str]:
        """Generate clarifying questions for resume tailoring.

        Args:
            job_data: Extracted job data
            profile_data: User profile data
            knowledge_context: Optional list of fact strings from knowledge base

        Returns:
            List of question strings

        Raises:
            RuntimeError: If unable to connect to Ollama after retries
        """
        spinner = SpinnerContextManager("🤖 Generating questions ")
        with spinner:
            try:
                if self._llm_service is not None:
                    result = self._llm_service.generate_questions(
                        job_data, profile_data, knowledge_context=knowledge_context
                    )
                    return result
            except Exception:
                pass
            result = run_async(self._generate_questions_async(job_data, profile_data))
            return result

    async def _generate_resume_async(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None,
        answers: list[str] | None,
        output_path: str,
    ) -> dict[str, Any]:
        """Async version of resume generation."""
        prompt = get_resume_prompt(job_data, profile_data, questions, answers)

        logger.header("Resume Generation")
        logger.llm_request(self.config.endpoint, self.config.model, len(prompt))
        logger.llm_call(
            "generate_resume",
            {
                "job_title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
                "has_questions": bool(questions),
                "has_answers": bool(answers),
            },
        )

        response = await asyncio.to_thread(
            self.client.chat,
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            format=ResumeContent.model_json_schema(),
            think=False,
            options={"temperature": 0.3, "num_predict": 5000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        try:
            resume_content = ResumeContent.model_validate_json(cleaned).model_dump()
        except Exception as e:
            Path(output_path).write_text(cleaned)
            logger.error(f"Failed to generate valid resume: {e}")
            logger.warning(f"Raw output saved to {output_path}")
            raise RuntimeError(
                f"Failed to generate valid resume.\n"
                f"  Raw LLM output saved to: {output_path}\n\n"
                f"  Suggestion: The model may have generated invalid JSON. Check the output file.\n"
                f"  Try again or use a different model."
            ) from e

        logger.llm_result(
            "resume",
            {
                "experience_count": len(
                    resume_content.get("sections", {}).get("experience", {}).get("items", [])
                ),
                "skills_count": len(
                    resume_content.get("sections", {}).get("skills", {}).get("items", [])
                ),
            },
        )

        return resume_content

    @with_retry(max_retries=3, initial_delay=2.0)
    def generate_cover_letter(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None = None,
        answers: list[str] | None = None,
        output_path: str = "debug_cover_letter_output.json",
    ) -> dict[str, Any]:
        """Generate a tailored cover letter from job and profile data.

        Args:
            job_data: Extracted job data
            profile_data: User profile data
            questions: Optional list of questions asked
            answers: Optional list of answers to questions
            output_path: Path to save raw LLM output on error

        Returns:
            Dict with 'recipient' and 'content' fields (CoverLetterContent)

        Raises:
            RuntimeError: If LLM fails to generate valid cover letter after retries
        """
        with SpinnerContextManager("✍️  Generating cover letter "):
            try:
                if self._llm_service is not None:
                    result = self._llm_service.generate_cover_letter(
                        job_data, profile_data, questions=questions, answers=answers
                    )
                    return result
            except Exception:
                pass
            result = run_async(
                self._generate_cover_letter_async(
                    job_data, profile_data, questions, answers, output_path
                )
            )
            return result

    async def _generate_cover_letter_async(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None,
        answers: list[str] | None,
        output_path: str,
    ) -> dict[str, Any]:
        """Async version of cover letter generation."""
        prompt = get_cover_letter_prompt(job_data, profile_data, questions, answers)

        logger.header("Cover Letter Generation")
        logger.llm_request(self.config.endpoint, self.config.model, len(prompt))
        logger.llm_call(
            "generate_cover_letter",
            {
                "job_title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
            },
        )

        response = await asyncio.to_thread(
            self.client.chat,
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            format=CoverLetterContent.model_json_schema(),
            think=False,
            options={"temperature": 0.7, "num_predict": 2000},
        )

        result = response.get("message", {}).get("content", "")
        cleaned = strip_markdown_json(result)

        logger.llm_response(len(cleaned))

        try:
            cover_letter_content = CoverLetterContent.model_validate_json(cleaned).model_dump()
        except (json.JSONDecodeError, Exception) as e:
            Path(output_path).write_text(cleaned)
            logger.error(f"Failed to parse cover letter JSON: {e}")
            logger.warning(f"Raw output saved to {output_path}")
            raise RuntimeError(
                f"Failed to parse cover letter.\n"
                f"  Raw LLM output saved to: {output_path}\n\n"
                f"  Suggestion: The model may have generated invalid JSON. Check the output file.\n"
                f"  Try again or use a different model."
            ) from e

        if not cover_letter_content.get("recipient") or not cover_letter_content.get("content"):
            Path(output_path).write_text(cleaned)
            logger.error("Missing required fields in cover letter response")
            logger.warning(f"Raw output saved to {output_path}")
            raise RuntimeError(
                f"Missing required fields in cover letter.\n"
                f"  Raw LLM output saved to: {output_path}\n\n"
                f"  Expected: 'recipient' and 'content' fields.\n"
                f"  Try again or check the output file."
            )

        logger.llm_result(
            "cover_letter",
            {
                "recipient": cover_letter_content.get("recipient", ""),
                "content_length": len(cover_letter_content.get("content", "")),
            },
        )

        return cover_letter_content

    @with_retry(max_retries=3, initial_delay=2.0)
    def generate_resume(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None = None,
        answers: list[str] | None = None,
        output_path: str = "debug_llm_output.json",
    ) -> dict[str, Any]:
        """Generate a tailored resume from job and profile data.

        Args:
            job_data: Extracted job data
            profile_data: User profile data
            questions: Optional list of questions asked
            answers: Optional list of answers to questions
            output_path: Path to save raw LLM output on error

        Returns:
            ResumeData as dict

        Raises:
            RuntimeError: If LLM fails to generate valid resume after retries
        """
        with SpinnerContextManager("📝 Generating resume "):
            try:
                if self._llm_service is not None:
                    result = self._llm_service.generate_resume(
                        job_data, profile_data, questions=questions, answers=answers
                    )
                    return result
            except Exception:
                pass
            result = run_async(
                self._generate_resume_async(job_data, profile_data, questions, answers, output_path)
            )
            return result

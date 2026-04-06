"""Ollama service for resume generation."""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from ollama import Client

from ..models import ResumeData
from ..prompts.resume import get_resume_prompt
from ..prompts.questions import get_questions_prompt, QuestionList
from ..prompts.cover_letter import get_cover_letter_prompt
from ..config import OllamaConfig
from ..log import logger


class OllamaService:
    """Service for interacting with Ollama for resume generation."""

    def __init__(self, config: OllamaConfig):
        self.config = config
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else None
        self.client = Client(host=config.endpoint, headers=headers)

    def _strip_markdown_json(self, content: str) -> str:
        """Strip markdown code blocks from LLM response if present."""
        content = content.strip()
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.match(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    def check_connection(self) -> bool:
        """Check if Ollama endpoint is reachable."""
        try:
            logger.api_request("GET", f"{self.config.endpoint}/api/tags")
            self.client.list()
            logger.api_response(200)
            return True
        except Exception as e:
            logger.error(f"Cannot connect to Ollama at {self.config.endpoint}: {e}")
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

    def generate_questions(
        self, job_data: Dict[str, Any], profile_data: Dict[str, Any]
    ) -> List[str]:
        """Generate clarifying questions for resume tailoring.

        Args:
            job_data: Extracted job data
            profile_data: User profile data

        Returns:
            List of question strings
        """
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

        try:
            response = self.client.chat(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                format=QuestionList.model_json_schema(),
                think=False,
                options={"temperature": 0.3, "num_predict": 1000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)

            logger.llm_response(len(cleaned))
            logger.llm_result("questions", {"count": len(cleaned)})

            question_list = QuestionList.model_validate_json(cleaned)
            questions = question_list.questions[:8]

            logger.llm_result("questions_parsed", {"count": len(questions)})
            for i, q in enumerate(questions, 1):
                logger.detail(f"Q{i}", q[:80] + "..." if len(q) > 80 else q)

            return questions

        except Exception as e:
            logger.error(f"Failed to generate questions: {e}")
            return []

    def generate_resume(
        self,
        job_data: Dict[str, Any],
        profile_data: Dict[str, Any],
        questions: Optional[List[str]] = None,
        answers: Optional[List[str]] = None,
        output_path: str = "debug_llm_output.json",
    ) -> Dict[str, Any]:
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
            RuntimeError: If LLM fails to generate valid resume
        """
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

        try:
            response = self.client.chat(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                format=ResumeData.model_json_schema(),
                think=False,
                options={"temperature": 0.3, "num_predict": 5000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)

            logger.llm_response(len(cleaned))

            resume_data = ResumeData.model_validate_json(cleaned).model_dump()

            logger.llm_result(
                "resume",
                {
                    "name": resume_data.get("basics", {}).get("name", "Unknown"),
                    "experience_count": len(
                        resume_data.get("sections", {}).get("experience", {}).get("items", [])
                    ),
                    "skills_count": len(
                        resume_data.get("sections", {}).get("skills", {}).get("items", [])
                    ),
                },
            )

            return resume_data

        except Exception as e:
            Path(output_path).write_text(cleaned if "cleaned" in dir() else result)
            logger.error(f"Failed to generate valid resume: {e}")
            logger.warning(f"Raw output saved to {output_path}")
            raise RuntimeError(
                f"Failed to generate valid resume. Raw output saved to {output_path}: {e}"
            )

    def generate_cover_letter(
        self,
        job_data: Dict[str, Any],
        profile_data: Dict[str, Any],
        questions: Optional[List[str]] = None,
        answers: Optional[List[str]] = None,
        output_path: str = "debug_cover_letter_output.json",
    ) -> Dict[str, Any]:
        """Generate a tailored cover letter from job and profile data.

        Args:
            job_data: Extracted job data
            profile_data: User profile data
            questions: Optional list of questions asked
            answers: Optional list of answers to questions
            output_path: Path to save raw LLM output on error

        Returns:
            Dict with 'recipient' and 'content' fields

        Raises:
            RuntimeError: If LLM fails to generate valid cover letter
        """
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

        try:
            response = self.client.chat(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
                format={
                    "type": "object",
                    "properties": {
                        "recipient": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["recipient", "content"],
                },
                think=False,
                options={"temperature": 0.7, "num_predict": 2000},
            )

            result = response.get("message", {}).get("content", "")
            cleaned = self._strip_markdown_json(result)

            logger.llm_response(len(cleaned))

            cover_letter_data = json.loads(cleaned)

            if "recipient" not in cover_letter_data or "content" not in cover_letter_data:
                raise ValueError("Missing required fields: recipient and content")

            logger.llm_result(
                "cover_letter",
                {
                    "recipient": cover_letter_data.get("recipient", ""),
                    "content_length": len(cover_letter_data.get("content", "")),
                },
            )

            return cover_letter_data

        except Exception as e:
            Path(output_path).write_text(cleaned if "cleaned" in dir() else result)
            logger.error(f"Failed to generate valid cover letter: {e}")
            logger.warning(f"Raw output saved to {output_path}")
            raise RuntimeError(
                f"Failed to generate valid cover letter. Raw output saved to {output_path}: {e}"
            )

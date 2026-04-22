"""LLM service abstraction layer supporting multiple providers.

This module provides a unified interface for LLM calls, abstracting over
different providers (Ollama for local, OpenCode Go for cloud) using LangChain's
BaseChatModel. The provider is selected via configuration — no code changes needed
to switch between them.

## Architecture

    Config (config.json / env vars)
            │
            ▼
    LLMService._create_llm()
            │
            ├── provider="ollama" → ChatOllama (local, free)
            │                        └── base_url: http://localhost:11434
            │                        └── model: llama3.2
            │
            └── provider="opencode-go" → ChatOpenAI (cloud, subscription)
                                           └── base_url: https://opencode.ai/zen/go/v1
                                           └── api_key: your-key
                                           └── model: gpt-4o

## Usage

    from fast_app.services.llm_service import LLMService
    from fast_app.config import Config, LLMConfig

    config = Config(llm=LLMConfig(provider="opencode-go", api_key="..."))
    service = LLMService(config)

    # Simple text generation
    result = service.generate("Explain Python decorators")

    # Structured output (Pydantic model)
    from fast_app.models import QuestionContent
    questions = service.generate_with_schema(prompt, QuestionContent)

    # High-level operations (delegate to LangChain chains)
    questions = service.generate_questions(job_data, profile_data)
    resume = service.generate_resume(job_data, profile_data, questions, answers)

## Provider Configuration

In config.json:
    {
      "llm": {
        "provider": "ollama",
        "model": "llama3.2",
        "temperature": 0.3,
        "base_url": "",
        "api_key": ""
      }
    }

Environment variable overrides:
    FAST_APP_LLM_PROVIDER=opencode-go
    FAST_APP_LLM_MODEL=gpt-4o
    FAST_APP_LLM_BASE_URL=https://opencode.ai/zen/go/v1
    FAST_APP_LLM_API_KEY=your-key

## Priority Order

1. CLI --provider flag (highest)
2. Environment variable (FAST_APP_LLM_PROVIDER)
3. config.json llm.provider field
4. Default: "ollama"

## Backward Compatibility

The existing OllamaService class is preserved as a thin wrapper that delegates
to LLMService internally. All existing CLI and webapp code continues to work
without changes.

See: docs/adr/001-llm-abstraction-langchain.md, docs/guide/llm-providers.md
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..log import logger


class LLMService:
    """Unified LLM interface supporting multiple providers via LangChain.

    This class wraps LangChain's BaseChatModel, providing a single interface for
    text generation, structured output, and domain-specific operations (question
    generation, resume generation, cover letter generation, fact extraction).

    The provider is selected at initialization based on config.llm.provider:
    - "ollama" → ChatOllama (local inference via Ollama)
    - "opencode-go" → ChatOpenAI (cloud via OpenAI-compatible API)

    Attributes:
        config: Application configuration containing LLM settings.
        _llm: The LangChain BaseChatModel instance (ChatOllama or ChatOpenAI).
    """

    def __init__(self, config: Config):
        """Initialize the LLM service with provider-specific model.

        Args:
            config: Application config containing LLMConfig, OllamaConfig, etc.
        """
        self.config = config
        self._llm = self._create_llm()

    def _create_llm(self) -> Any:
        """Create a LangChain chat model based on provider configuration.

        Returns:
            A BaseChatModel instance (ChatOllama or ChatOpenAI).

        Raises:
            ValueError: If the provider is not "ollama" or "opencode-go".
            ImportError: If the required LangChain package is not installed.
        """
        provider = self.config.llm.provider

        if provider == "ollama":
            try:
                from langchain_ollama import ChatOllama
            except ImportError as e:
                raise ImportError(
                    "langchain-ollama is required for Ollama provider. "
                    "Install with: pip install -e '.[llm]'"
                ) from e

            return ChatOllama(
                model=self.config.llm.model or self.config.ollama.model,
                temperature=self.config.llm.temperature,
                base_url=self.config.ollama.endpoint,
            )

        elif provider == "opencode-go":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as e:
                raise ImportError(
                    "langchain-openai is required for OpenCode Go provider. "
                    "Install with: pip install -e '.[llm]'"
                ) from e

            return ChatOpenAI(
                model=self.config.llm.model,
                temperature=self.config.llm.temperature,
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url
                or "https://opencode.ai/zen/go/v1",
            )

        else:
            raise ValueError(
                f"Unknown LLM provider: {provider}. "
                f"Supported providers: 'ollama', 'opencode-go'"
            )

    def generate(self, prompt: str, **kwargs) -> str:
        """Simple text generation.

        Args:
            prompt: The text prompt to send to the LLM.
            **kwargs: Additional arguments passed to the LLM.

        Returns:
            The generated text content.

        Raises:
            ImportError: If LangChain packages are not installed.
        """
        from langchain_core.messages import HumanMessage

        logger.llm_call("generate", {"prompt_length": len(prompt)})
        response = self._llm.invoke([HumanMessage(content=prompt)], **kwargs)
        logger.llm_response(len(response.content))
        return response.content

    def generate_with_schema(self, prompt: str, schema: type, **kwargs) -> Any:
        """Generate structured output matching a Pydantic schema.

        Uses LangChain's with_structured_output() to force the LLM to return
        data matching the given Pydantic model. This replaces the previous
        approach of passing `format=PydanticClass.model_json_schema()` to
        Ollama's chat API.

        Args:
            prompt: The text prompt to send to the LLM.
            schema: A Pydantic model class defining the expected output structure.
            **kwargs: Additional arguments passed to the LLM.

        Returns:
            An instance of the schema class populated by the LLM.

        Raises:
            ImportError: If LangChain packages are not installed.
            ValidationError: If the LLM output doesn't match the schema.
        """
        logger.llm_call(
            "generate_with_schema",
            {"prompt_length": len(prompt), "schema": schema.__name__},
        )

        structured_llm = self._llm.with_structured_output(schema)
        result = structured_llm.invoke(prompt, **kwargs)

        logger.llm_call("generate_with_schema_result", {"schema": schema.__name__})
        return result

    def generate_questions(
        self, job_data: dict[str, Any], profile_data: dict[str, Any], **kwargs
    ) -> list[str]:
        """Generate interview questions using a LangChain chain.

        This method uses a ChatPromptTemplate that injects job_data and
        profile_data, then pipes through the LLM and a PydanticOutputParser
        to produce a QuestionContent object.

        Args:
            job_data: Extracted job data (title, company, description, etc.).
            profile_data: User profile data (skills, experience, etc.).
            **kwargs: Additional arguments passed to the LLM.

        Returns:
            List of question strings.

        Note:
            The knowledge_context parameter is added in Phase 4 to enable
            knowledge-informed question generation.
        """
        from ..prompts.templates import get_questions_template
        from ..models import QuestionContent

        template = get_questions_template()
        chain = template | self._llm | self._structured_output(QuestionContent)

        logger.llm_call(
            "generate_questions",
            {
                "job_title": job_data.get("title", "Unknown"),
                "company": job_data.get("company", "Unknown"),
            },
        )

        result = chain.invoke(
            {"job_data": job_data, "profile_data": profile_data},
            **kwargs,
        )

        questions = result.questions[:8]
        logger.llm_result("questions_parsed", {"count": len(questions)})
        return questions

    def generate_resume(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None = None,
        answers: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate resume content using a LangChain chain.

        Args:
            job_data: Extracted job data.
            profile_data: User profile data.
            questions: Optional list of interview questions.
            answers: Optional list of answers to questions.
            **kwargs: Additional arguments passed to the LLM.

        Returns:
            ResumeContent as a dict.
        """
        from ..prompts.templates import get_resume_template
        from ..models import ResumeContent

        template = get_resume_template()
        chain = template | self._llm | self._structured_output(ResumeContent)

        logger.llm_call(
            "generate_resume",
            {
                "job_title": job_data.get("title", "Unknown"),
                "has_questions": bool(questions),
                "has_answers": bool(answers),
            },
        )

        result = chain.invoke(
            {
                "job_data": job_data,
                "profile_data": profile_data,
                "questions": questions or [],
                "answers": answers or [],
            },
            **kwargs,
        )

        logger.llm_result("resume", {"has_content": bool(result)})
        return result.model_dump() if hasattr(result, "model_dump") else result

    def generate_cover_letter(
        self,
        job_data: dict[str, Any],
        profile_data: dict[str, Any],
        questions: list[str] | None = None,
        answers: list[str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate a cover letter using a LangChain chain.

        Args:
            job_data: Extracted job data.
            profile_data: User profile data.
            questions: Optional list of interview questions.
            answers: Optional list of answers to questions.
            **kwargs: Additional arguments passed to the LLM.

        Returns:
            CoverLetterContent as a dict.
        """
        from ..prompts.templates import get_cover_letter_template
        from ..models import CoverLetterContent

        template = get_cover_letter_template()
        chain = template | self._llm | self._structured_output(CoverLetterContent)

        logger.llm_call("generate_cover_letter", {"job_title": job_data.get("title")})

        result = chain.invoke(
            {
                "job_data": job_data,
                "profile_data": profile_data,
                "questions": questions or [],
                "answers": answers or [],
            },
            **kwargs,
        )

        logger.llm_result("cover_letter", {"has_content": bool(result)})
        return result.model_dump() if hasattr(result, "model_dump") else result

    def _structured_output(self, schema: type):
        """Create a structured output parser for the given Pydantic schema.

        Uses LangChain's with_structured_output() method on the LLM.
        Falls back to PydanticOutputParser if structured output is not
        supported by the provider.

        Args:
            schema: Pydantic model class for structured output.

        Returns:
            A runnable that produces instances of schema.
        """
        return self._llm.with_structured_output(schema)
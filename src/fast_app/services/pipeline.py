"""Shared pipeline service for job processing.

Extracts the duplicated job processing pipeline from cli.py and
webapp/background_tasks.py into a single service with callback-based I/O.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..config import Config
from ..log import logger
from ..services.cache import CacheManager, generate_job_id
from ..services.job_extractor import JobExtractor
from ..services.ollama import OllamaService
from ..services.reactive_resume import ReactiveResumeClient
from ..utils import (
    merge_cover_letter_with_base,
    merge_resume_with_base,
    sanitize_name,
)


@dataclass
class PipelineFlags:
    """Flags controlling pipeline behavior."""

    force: bool = False
    overwrite_resume: bool = False
    skip_questions: bool = False
    skip_cover_letter: bool = False
    no_knowledge: bool = False
    review_facts: bool = False
    debug: bool = False
    verbose: bool = False


@dataclass
class PipelineResult:
    """Result of a pipeline run."""

    resume_url: str
    cover_letter_url: str | None
    job_dir: Path
    job_data: dict[str, Any]
    resume_data: dict[str, Any]
    cover_letter_data: dict[str, Any] | None
    job_title: str
    company: str
    effective_url: str


@runtime_checkable
class PipelineCallbacks(Protocol):
    """Interface for pipeline I/O callbacks.

    Implementations provide I/O-specific operations that differ
    between CLI (Click-based) and webapp (async + WebSocket) contexts.
    """

    async def on_state_change(self, old_state: str, new_state: str) -> None:
        """Called when the pipeline state changes."""
        ...

    async def on_progress(self, step: str, progress: float) -> None:
        """Called when progress updates."""
        ...

    def on_job_extracted(self, job_title: str, company: str) -> None:
        """Called after job data is extracted/found."""
        ...

    def on_cache_hit(self, item: str, path: str) -> None:
        """Called when cached data is used."""
        ...

    def on_cache_save(self, item: str, path: str) -> None:
        """Called when data is saved to cache."""
        ...

    async def collect_answers(self, questions: list[str]) -> list[str]:
        """Collect answers to generated questions.

        CLI: Uses Click prompts interactively.
        Webapp: Uses StateManager + WebSocket broadcast.
        """
        ...

    def review_facts(self, facts: list) -> list | None:
        """Review extracted facts before storing.

        Return the facts to store, or None to skip storage.
        CLI: Uses click.confirm() for review.
        Webapp: Always returns facts as-is (auto-accept).
        """
        ...

    def raise_already_exists(self, item_type: str, identifier: str) -> None:
        """Raise an error when a resume/cover letter already exists.

        CLI: Raises click.ClickException.
        Webapp: Raises ValueError.
        """
        ...


class PipelineService:
    """Shared pipeline service for job processing.

    Contains the common pipeline logic used by both CLI and webapp,
    with I/O-specific operations delegated to PipelineCallbacks.
    """

    def __init__(
        self,
        config: Config,
        ollama: OllamaService,
        cache: CacheManager,
        rr_client: ReactiveResumeClient,
        profile: dict[str, Any],
        base_resume: dict[str, Any] | None,
        base_cover_letter: dict[str, Any] | None,
        callbacks: PipelineCallbacks,
        user_id: int = 1,
    ):
        self.config = config
        self.ollama = ollama
        self.cache = cache
        self.rr_client = rr_client
        self.profile = profile
        self.base_resume = base_resume
        self.base_cover_letter = base_cover_letter
        self.callbacks = callbacks
        self.user_id = user_id

    async def run(
        self,
        url: str,
        flags: PipelineFlags,
        job_title_input: str | None = None,
        content: str | None = None,
        job_url_opt: str | None = None,
    ) -> PipelineResult:
        """Run the full job processing pipeline.

        Args:
            url: Job URL (empty string in text mode).
            flags: Pipeline flags.
            job_title_input: Job title for text input mode.
            content: Job description text for text input mode.
            job_url_opt: Original job URL for metadata (text mode).

        Returns:
            PipelineResult with final data and URLs.
        """
        text_mode = bool(job_title_input and content)

        if text_mode:
            job_id = generate_job_id(content)
            effective_url = job_url_opt or ""
        else:
            job_id = generate_job_id(url)
            effective_url = url

        # State: idle -> processing
        await self.callbacks.on_state_change("idle", "processing")

        # Phase 1: Job Extraction
        (
            job_data,
            job_title,
            company,
            job_description,
            job_dir,
            questions,
            answers,
            used_cache,
        ) = await self._extract_job(
            url, text_mode, flags, job_id, job_title_input, content, effective_url
        )

        # Phase 2-4: Questions, Answers, Facts
        questions, answers = await self._generate_questions_and_answers(
            url, effective_url, flags, job_data, job_dir, questions, answers, used_cache
        )

        # Phase 5: Resume Generation
        await self.callbacks.on_progress("Generating resume", 0.5)
        resume_data = await self._generate_resume(flags, job_data, questions, answers, job_dir)

        # Phase 6: Cover Letter Generation
        cover_letter_data = None
        if not flags.skip_cover_letter:
            await self.callbacks.on_progress("Generating cover letter", 0.7)
            cover_letter_data = await self._generate_cover_letter(
                flags, job_data, questions, answers, job_title, company, job_dir
            )

        # Phase 7: Upload to Reactive Resume
        await self.callbacks.on_progress("Uploading to Reactive Resume", 0.85)
        resume_url, cover_letter_url = await self._upload_to_reactive_resume(
            flags,
            job_data,
            resume_data,
            cover_letter_data,
            job_title,
            company,
            effective_url,
            job_description,
            job_dir,
        )

        # State: processing -> complete
        await self.callbacks.on_state_change("processing", "complete")

        logger.success("Job completed successfully!")

        return PipelineResult(
            resume_url=resume_url,
            cover_letter_url=cover_letter_url,
            job_dir=job_dir,
            job_data=job_data,
            resume_data=resume_data,
            cover_letter_data=cover_letter_data,
            job_title=job_title,
            company=company,
            effective_url=effective_url,
        )

    async def _extract_job(
        self,
        url: str,
        text_mode: bool,
        flags: PipelineFlags,
        job_id: str,
        job_title_input: str | None,
        content: str | None,
        effective_url: str,
    ) -> tuple[dict[str, Any], str, str, str, Path, list[str], list[str], bool]:
        """Extract job data, checking cache first.

        Returns tuple of:
        (job_data, job_title, company, job_description,
         job_dir, questions, answers, used_cache)
        """
        questions: list[str] = []
        answers: list[str] = []
        used_cache = False

        # Check cache first (URL mode only)
        if not text_mode:
            existing_job_dir = self.cache.has_cached_job(url)
            if existing_job_dir and not flags.force:
                used_cache = True
                job_data = self.cache.get_cached_job(existing_job_dir) or {}
                raw_title = job_data.get("title", "Unknown")
                raw_company = job_data.get("company", "Unknown")
                job_title = sanitize_name(raw_title)
                company = sanitize_name(raw_company)
                job_description = job_data.get("description", "")
                job_dir = existing_job_dir

                self.callbacks.on_cache_hit("job", str(existing_job_dir))

                if not flags.skip_questions:
                    questions_path = existing_job_dir / "questions.json"
                    answers_path = existing_job_dir / "answers.json"
                    if questions_path.exists() and answers_path.exists():
                        questions = self.cache.get_cached_questions(existing_job_dir) or []
                        answers = self.cache.get_cached_answers(existing_job_dir) or []
                        self.callbacks.on_cache_hit("questions", str(questions_path))
                        self.callbacks.on_cache_hit("answers", str(answers_path))

        if not used_cache:
            await self.callbacks.on_progress("Extracting job data", 0.1)

            extractor = JobExtractor(self.ollama.client, self.config.ollama.model)
            if text_mode:
                job_data = await asyncio.to_thread(
                    extractor.extract_from_text, job_title_input, content, url=effective_url
                )
            else:
                job_data = await asyncio.to_thread(extractor.extract_from_url, url)

            raw_title = job_data.get("title", "Unknown")
            raw_company = job_data.get("company", "Unknown")
            job_title = sanitize_name(raw_title)
            company = sanitize_name(raw_company)
            job_description = job_data.get("description", "")

            self.callbacks.on_job_extracted(job_title, company)

            logger.detail("job_id", job_id)
            logger.detail("company", company)
            logger.detail("title", job_title)

            job_dir = self.cache.get_job_dir(company, job_title, job_id, create=True)
            self.cache.save_job(job_dir, job_data)
            self.callbacks.on_cache_save("job", str(job_dir / "job.json"))

            if not flags.skip_questions:
                questions_path = job_dir / "questions.json"
                answers_path = job_dir / "answers.json"
                if not flags.force and questions_path.exists() and answers_path.exists():
                    questions = self.cache.get_cached_questions(job_dir) or []
                    answers = self.cache.get_cached_answers(job_dir) or []
                    self.callbacks.on_cache_hit("questions", str(questions_path))
                    self.callbacks.on_cache_hit("answers", str(answers_path))

        return (
            job_data,
            job_title,
            company,
            job_description,
            job_dir,
            questions,
            answers,
            used_cache,
        )

    async def _generate_questions_and_answers(
        self,
        url: str,
        effective_url: str,
        flags: PipelineFlags,
        job_data: dict[str, Any],
        job_dir: Path,
        questions: list[str],
        answers: list[str],
        used_cache: bool,
    ) -> tuple[list[str], list[str]]:
        """Generate questions, collect answers, and extract facts.

        Returns (questions, answers).
        """
        # If we already have cached Q&A or are skipping, return early
        if flags.skip_questions:
            return questions, answers

        if questions and answers:
            return questions, answers

        await self.callbacks.on_progress("Generating questions", 0.25)

        knowledge_facts = None
        if not flags.no_knowledge:
            try:
                from ..services.knowledge import KnowledgeService

                knowledge_svc = KnowledgeService(self.config, user_id=self.user_id)
                results = knowledge_svc.query_facts(
                    f"{job_data.get('title', '')} {job_data.get('description', '')[:200]}",
                    n=5,
                )
                if results:
                    knowledge_facts = [r.content for r in results]
                    logger.info(f"Injected {len(results)} facts from knowledge base")
            except ImportError:
                pass
            except Exception:
                pass

        generated_questions = await asyncio.to_thread(
            self.ollama.generate_questions,
            job_data,
            self.profile,
            knowledge_context=knowledge_facts,
        )

        if not generated_questions:
            logger.warning("No questions generated, proceeding with resume creation.")
            return [], []

        questions = generated_questions
        self.cache.save_questions(job_dir, questions)
        self.callbacks.on_cache_save("questions", str(job_dir / "questions.json"))

        answers = await self.callbacks.collect_answers(questions)

        self.cache.save_answers(job_dir, answers)
        self.callbacks.on_cache_save("answers", str(job_dir / "answers.json"))

        if not flags.no_knowledge and questions and answers:
            try:
                from ..services.fact_extractor import FactExtractor
                from ..services.knowledge import KnowledgeService
                from ..services.llm_service import LLMService

                llm_service = LLMService(self.config)
                fact_extractor = FactExtractor(llm_service)
                result = fact_extractor.extract_facts_from_answers(
                    questions, answers, profile_data=self.profile, job_data=job_data
                )
                if result.facts:
                    facts_to_store = self.callbacks.review_facts(result.facts)
                    if facts_to_store:
                        knowledge_svc = KnowledgeService(self.config, user_id=self.user_id)
                        stored_ids = knowledge_svc.store_facts(
                            facts_to_store, job_url=effective_url or url
                        )
                        logger.success(f"Stored {len(stored_ids)} facts in knowledge base")
            except ImportError:
                logger.warning("Knowledge dependencies not installed, skipping fact extraction")
            except Exception as e:
                logger.warning(f"Fact extraction failed: {e}")

        return questions, answers

    async def _generate_resume(
        self,
        flags: PipelineFlags,
        job_data: dict[str, Any],
        questions: list[str],
        answers: list[str],
        job_dir: Path,
    ) -> dict[str, Any]:
        """Generate or load resume data.

        Returns the merged resume data dict.
        """
        resume_path = job_dir / "resume.json"

        if not flags.force and resume_path.exists():
            resume_data = self.cache.get_cached_resume(job_dir)
            self.callbacks.on_cache_hit("resume", str(resume_path))
            return resume_data

        resume_content = await asyncio.to_thread(
            self.ollama.generate_resume,
            job_data,
            self.profile,
            questions=questions or None,
            answers=answers or None,
            output_path=str(job_dir / "debug_llm_output.json"),
        )

        resume_data = merge_resume_with_base(resume_content, self.profile, self.base_resume)
        self.cache.save_resume(job_dir, resume_data)
        self.callbacks.on_cache_save("resume", str(resume_path))

        return resume_data

    async def _generate_cover_letter(
        self,
        flags: PipelineFlags,
        job_data: dict[str, Any],
        questions: list[str],
        answers: list[str],
        job_title: str,
        company: str,
        job_dir: Path,
    ) -> dict[str, Any] | None:
        """Generate or load cover letter data.

        Returns the merged cover letter data dict, or None if skipped.
        """
        cover_letter_path = job_dir / "cover_letter.json"

        if not flags.force and cover_letter_path.exists():
            cover_letter_data = self.cache.get_cached_cover_letter(job_dir)
            self.callbacks.on_cache_hit("cover_letter", str(cover_letter_path))
            return cover_letter_data

        cover_letter_content = await asyncio.to_thread(
            self.ollama.generate_cover_letter,
            job_data,
            self.profile,
            questions=questions or None,
            answers=answers or None,
            output_path=str(job_dir / "debug_cover_letter_output.json"),
        )

        cover_letter_data = merge_cover_letter_with_base(
            cover_letter_content, self.profile, self.base_cover_letter, job_title, company
        )

        self.cache.save_cover_letter(job_dir, cover_letter_data)
        self.callbacks.on_cache_save("cover_letter", str(cover_letter_path))

        return cover_letter_data

    async def _upload_to_reactive_resume(
        self,
        flags: PipelineFlags,
        job_data: dict[str, Any],
        resume_data: dict[str, Any],
        cover_letter_data: dict[str, Any] | None,
        job_title: str,
        company: str,
        effective_url: str,
        job_description: str,
        job_dir: Path,
    ) -> tuple[str, str | None]:
        """Upload resume and cover letter to Reactive Resume.

        Returns (resume_url, cover_letter_url).
        """
        resume_title = f"{job_title} at {company} Resume"

        existing_resume_id = self._check_existing_item(
            job_dir, "reactive_resume.json", "resume_id", flags.overwrite_resume
        )
        if existing_resume_id and not flags.overwrite_resume:
            self.callbacks.raise_already_exists("resume", resume_title)

        if existing_resume_id and flags.overwrite_resume:
            self.rr_client.delete_resume(existing_resume_id)

        resume_data["metadata"]["notes"] = f"{effective_url}\n\n{job_description}"

        resume_id = self.rr_client.create_resume(resume_title, tags=[company])
        self.rr_client.update_resume(resume_id, resume_data)

        self.cache.save_reactive_resume(job_dir, {"resume_id": resume_id, "title": resume_title})
        self.callbacks.on_cache_save("reactive_resume", str(job_dir / "reactive_resume.json"))

        resume_url = self.rr_client.get_resume_url(resume_id)
        logger.success(f"Resume created: {resume_url}")

        # Create cover letter if requested
        cover_letter_url = None

        if not flags.skip_cover_letter and cover_letter_data:
            cover_letter_title = f"{job_title} at {company} Cover Letter"

            existing_cl_id = self._check_existing_item(
                job_dir, "reactive_cover_letter.json", "cover_letter_id", flags.overwrite_resume
            )
            if existing_cl_id and not flags.overwrite_resume:
                self.callbacks.raise_already_exists("cover_letter", cover_letter_title)

            if existing_cl_id and flags.overwrite_resume:
                self.rr_client.delete_resume(existing_cl_id)

            cover_letter_data["metadata"]["notes"] = f"{effective_url}\n\n{job_description}"

            cover_letter_id = self.rr_client.create_resume(
                cover_letter_title, tags=[company], slug_prefix="cl"
            )
            self.rr_client.update_resume(cover_letter_id, cover_letter_data)

            self.cache.save_reactive_cover_letter(
                job_dir,
                {"cover_letter_id": cover_letter_id, "title": cover_letter_title},
            )
            self.callbacks.on_cache_save(
                "reactive_cover_letter", str(job_dir / "reactive_cover_letter.json")
            )

            cover_letter_url = self.rr_client.get_resume_url(cover_letter_id)
            logger.success(f"Cover letter created: {cover_letter_url}")

        return resume_url, cover_letter_url

    def _check_existing_item(
        self,
        job_dir: Path,
        cache_filename: str,
        id_field: str,
        overwrite: bool,
    ) -> str | None:
        """Check if a resume/cover letter already exists in Reactive Resume.

        Returns the existing ID if found, None otherwise.
        If overwrite is True and the item exists, deletes it and returns None.
        """
        cache_path = job_dir / cache_filename
        if not cache_path.exists():
            return None

        import json

        try:
            cached = json.loads(cache_path.read_text())
            item_id = cached.get(id_field)
            if not item_id:
                return None

            existing = self.rr_client.get_resume(item_id)
            if existing:
                return item_id
        except Exception:
            pass

        return None

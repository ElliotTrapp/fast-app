"""Background task processing for webapp."""

import asyncio
from pathlib import Path

from ..config import load_config
from ..log import logger
from ..services.cache import CacheManager, generate_job_id
from ..services.job_extractor import JobExtractor
from ..services.ollama import OllamaService
from ..services.reactive_resume import ReactiveResumeClient
from ..utils import (
    check_existing_cover_letter,
    check_existing_resume,
    load_base_cover_letter,
    load_base_resume,
    load_profile,
    merge_cover_letter_with_base,
    merge_resume_with_base,
    sanitize_name,
)
from .state import JobState


async def process_job(url: str, flags: dict[str, bool], state, broadcast_callback) -> None:
    """Process a job asynchronously in the background.

    Args:
        url: Job URL
        flags: CLI flags (force, debug, etc.)
        state: StateManager instance
        broadcast_callback: Async function to broadcast updates
    """
    try:
        # Load configuration
        config = load_config(None)

        # Initialize services
        ollama = OllamaService(config.ollama)
        cache = CacheManager(Path.cwd() / config.output.directory)
        rr_client = ReactiveResumeClient(config.resume.endpoint, config.resume.api_key)

        # Load profile and base resume
        profile = load_profile(None)
        base_resume = load_base_resume(None)
        base_cover_letter = load_base_cover_letter(None)

        # Update state
        job_id = generate_job_id(url)
        state.start_job(job_id, url, flags)
        await broadcast_callback(
            {"type": "state_change", "old_state": "idle", "new_state": "processing"}
        )

        # Extract job data
        state.update_progress("Extracting job data", 0.1)
        logger.info(f"Extracting job from: {url}")

        job_extractor = JobExtractor(ollama.client, config.ollama.model)
        job_data = await asyncio.to_thread(job_extractor.extract_from_url, url)

        raw_title = job_data.get("title", "Unknown")
        raw_company = job_data.get("company", "Unknown")
        job_title = sanitize_name(raw_title)
        company = sanitize_name(raw_company)
        job_description = job_data.get("description", "")

        state.company = company
        state.title = job_title
        state.save()

        logger.success(f"Found: {job_title} at {company}")

        # Check for cached job
        job_dir = cache.get_job_dir(company, job_title, job_id, create=True)

        if not flags.get("force") and state.job_id:
            existing_dir = cache.has_cached_job(url)
            if existing_dir:
                cached_job = cache.get_cached_job(existing_dir)
                if cached_job:
                    job_data = cached_job
                    logger.success("Using cached job data")

        # Save job data
        cache.save_job(job_dir, job_data)

        # Generate questions
        state.update_progress("Checking for cached questions", 0.2)

        questions = []
        answers = []

        questions_path = job_dir / "questions.json"
        answers_path = job_dir / "answers.json"

        if not flags.get("force") and questions_path.exists() and answers_path.exists():
            questions = cache.get_cached_questions(job_dir) or []
            answers = cache.get_cached_answers(job_dir) or []
            logger.success("Using cached questions and answers")
        elif not flags.get("skip_questions"):
            state.update_progress("Generating questions", 0.25)
            logger.info("Generating questions...")

            questions = await asyncio.to_thread(ollama.generate_questions, job_data, profile)

            if questions:
                cache.save_questions(job_dir, questions)
                logger.success(f"Generated {len(questions)} questions")

                # Transition to waiting_questions state
                state.set_waiting_questions(questions)
                await broadcast_callback(
                    {
                        "type": "state_change",
                        "old_state": "processing",
                        "new_state": "waiting_questions",
                    }
                )

                # Wait for answers to be submitted via POST /api/answer
                while state.state == JobState.WAITING_QUESTIONS:
                    await asyncio.sleep(0.5)

                answers = state.answers

                # Save answers
                cache.save_answers(job_dir, answers)
                logger.success(f"Saved {len(answers)} answers")

                # Transition back to processing
                await broadcast_callback(
                    {
                        "type": "state_change",
                        "old_state": "waiting_questions",
                        "new_state": "processing",
                    }
                )

        # Generate resume content from LLM
        state.update_progress("Generating resume", 0.5)
        logger.info("Generating resume...")

        resume_path = job_dir / "resume.json"

        if not flags.get("force") and resume_path.exists():
            resume_data = cache.get_cached_resume(job_dir)
            logger.success("Using cached resume data")
        else:
            resume_content = await asyncio.to_thread(
                ollama.generate_resume,
                job_data,
                profile,
                questions=questions if questions else None,
                answers=answers if answers else None,
                output_path=str(job_dir / "debug_llm_output.json"),
            )

            # Merge with base and profile
            final_resume = merge_resume_with_base(resume_content, profile, base_resume)

            # Save merged result
            cache.save_resume(job_dir, final_resume)
            logger.success("Saved resume")

        # Generate cover letter content from LLM
        cover_letter_url = None

        if not flags.get("skip_cover_letter"):
            state.update_progress("Generating cover letter", 0.7)
            logger.info("Generating cover letter...")

            cover_letter_path = job_dir / "cover_letter.json"

            if not flags.get("force") and cover_letter_path.exists():
                cover_letter_data = cache.get_cached_cover_letter(job_dir)
                logger.success("Using cached cover letter data")
            else:
                cover_letter_content = await asyncio.to_thread(
                    ollama.generate_cover_letter,
                    job_data,
                    profile,
                    questions=questions if questions else None,
                    answers=answers if answers else None,
                    output_path=str(job_dir / "debug_cover_letter_output.json"),
                )

                # Merge with base and profile
                final_cover_letter = merge_cover_letter_with_base(
                    cover_letter_content, profile, base_cover_letter, job_title, company
                )

                # Save merged result
                cache.save_cover_letter(job_dir, final_cover_letter)
                logger.success("Saved cover letter")

        # Upload to Reactive Resume
        state.update_progress("Uploading to Reactive Resume", 0.85)
        logger.info("Uploading to Reactive Resume...")

        # Load final resume
        resume_data = cache.get_cached_resume(job_dir)
        resume_title = f"{job_title} at {company} Resume"

        # Check for existing resume
        existing_resume_id = check_existing_resume(
            rr_client, cache, job_dir, flags.get("overwrite_resume", False)
        )

        if existing_resume_id and not flags.get("overwrite_resume", False):
            raise ValueError("Resume already exists. Use --overwrite-resume to replace.")

        # Add notes with URL and description
        resume_data["metadata"]["notes"] = f"{url}\n\n{job_description}"

        # Create resume
        resume_id = rr_client.create_resume(resume_title, tags=[company])
        rr_client.update_resume(resume_id, resume_data)

        # Cache resume metadata
        cache.save_reactive_resume(job_dir, {"resume_id": resume_id, "title": resume_title})

        resume_url = rr_client.get_resume_url(resume_id)
        logger.success(f"Resume created: {resume_url}")

        # Upload cover letter
        if not flags.get("skip_cover_letter"):
            cover_letter_data = cache.get_cached_cover_letter(job_dir)
            cover_letter_title = f"{job_title} at {company} Cover Letter"

            # Check for existing cover letter
            existing_cl_id = check_existing_cover_letter(
                rr_client, cache, job_dir, flags.get("overwrite_resume", False)
            )

            if existing_cl_id and not flags.get("overwrite_resume", False):
                raise ValueError("Cover letter already exists. Use --overwrite-resume to replace.")

            # Add notes
            cover_letter_data["metadata"]["notes"] = f"{url}\n\n{job_description}"

            # Create cover letter
            cover_letter_id = rr_client.create_resume(
                cover_letter_title, tags=[company], slug_prefix="cl"
            )
            rr_client.update_resume(cover_letter_id, cover_letter_data)

            # Cache cover letter metadata
            cache.save_reactive_cover_letter(
                job_dir, {"cover_letter_id": cover_letter_id, "title": cover_letter_title}
            )

            cover_letter_url = rr_client.get_resume_url(cover_letter_id)
            logger.success(f"Cover letter created: {cover_letter_url}")

        # Mark complete
        state.set_complete(resume_url, cover_letter_url)
        await broadcast_callback(
            {"type": "state_change", "old_state": "processing", "new_state": "complete"}
        )
        await broadcast_callback(
            {"type": "complete", "resume_url": resume_url, "cover_letter_url": cover_letter_url}
        )

        logger.success("Job completed successfully!")

    except Exception as e:
        import traceback

        error_msg = f"{str(e)}\n\n{traceback.format_exc()}"
        logger.error(f"Job failed: {str(e)}")
        state.set_error(error_msg)
        await broadcast_callback(
            {"type": "state_change", "old_state": state.state, "new_state": "error"}
        )
        await broadcast_callback(
            {"type": "error", "message": str(e), "traceback": traceback.format_exc()}
        )

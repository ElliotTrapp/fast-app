"""Background task processing for webapp."""

from pathlib import Path

from ..config import load_config
from ..log import logger
from ..services.cache import CacheManager, generate_job_id
from ..services.ollama import OllamaService
from ..services.pipeline import PipelineFlags, PipelineService
from ..services.reactive_resume import ReactiveResumeClient
from ..utils import (
    load_base_cover_letter,
    load_base_resume,
    load_profile,
)
from .webapp_callbacks import WebappCallbacks


async def process_job(
    url: str,
    flags: dict[str, bool],
    state,
    broadcast_callback,
    title: str | None = None,
    content: str | None = None,
    user_id: int = 1,
) -> None:
    """Process a job asynchronously in the background.

    Args:
        url: Job URL (empty string in text mode)
        flags: CLI flags (force, debug, etc.)
        state: StateManager instance
        broadcast_callback: Async function to broadcast updates
        title: Job title for text input mode
        content: Job description text for text input mode
        user_id: User ID for per-user knowledge service
    """
    try:
        # Load configuration
        config = load_config(None)

        # Initialize services
        ollama = OllamaService(config.ollama)
        cache = CacheManager(Path.cwd() / config.output.directory)
        rr_client = ReactiveResumeClient(
            config.reactive_resume.endpoint, config.reactive_resume.api_key
        )

        # Load profile and base resume
        profile = load_profile(None)
        base_resume = load_base_resume(None)
        base_cover_letter = load_base_cover_letter(None)

        # Determine text vs URL mode
        text_mode = bool(title and content)

        # Compute job ID and start job state
        if text_mode:
            job_id = generate_job_id(content)
        else:
            job_id = generate_job_id(url)
        state.start_job(job_id, url, flags)

        # Initialize callbacks and pipeline
        callbacks = WebappCallbacks(state=state, broadcast_callback=broadcast_callback)
        pipeline_flags = PipelineFlags(
            force=flags.get("force", False),
            overwrite_resume=flags.get("overwrite_resume", False),
            skip_questions=flags.get("skip_questions", False),
            skip_cover_letter=flags.get("skip_cover_letter", False),
            no_knowledge=flags.get("no_knowledge", False),
            review_facts=flags.get("review_facts", False),
            debug=flags.get("debug", False),
            verbose=flags.get("verbose", False),
        )

        pipeline = PipelineService(
            config=config,
            ollama=ollama,
            cache=cache,
            rr_client=rr_client,
            profile=profile,
            base_resume=base_resume,
            base_cover_letter=base_cover_letter,
            callbacks=callbacks,
            user_id=user_id,
        )

        # Run the pipeline
        result = await pipeline.run(
            url=url,
            flags=pipeline_flags,
            job_title_input=title,
            content=content,
        )

        # Mark complete with result URLs
        state.set_complete(result.resume_url, result.cover_letter_url)
        await broadcast_callback(
            {
                "type": "complete",
                "resume_url": result.resume_url,
                "cover_letter_url": result.cover_letter_url,
            }
        )

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

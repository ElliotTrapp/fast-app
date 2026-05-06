"""Main CLI group and generate command."""

import asyncio
import json
from pathlib import Path

import click

from ..config import load_config
from ..log import logger
from ..services.cache import CacheManager
from ..services.cli_callbacks import CLICallbacks
from ..services.ollama import OllamaService
from ..services.pipeline import PipelineFlags, PipelineService
from ..services.reactive_resume import ReactiveResumeClient
from ..utils import (
    load_base_cover_letter,
    load_base_resume,
    load_profile,
)


@click.group()
@click.version_option(version="1.0.0")
def main():
    """Fast App: Generate tailored resumes from job URLs."""
    pass


@main.command()
@click.argument("url", required=False)
@click.option(
    "--text",
    "-t",
    "job_title",
    default=None,
    help="Job title for text input mode (use instead of URL)",
)
@click.option(
    "--content",
    default=None,
    help="Job description text (required with --text)",
)
@click.option(
    "--job-url",
    "job_url_opt",
    default=None,
    help="Original job URL for metadata (optional, used with --text)",
)
@click.option(
    "--profile",
    "-p",
    "profile_path",
    default=None,
    help="Path to profile JSON file",
)
@click.option(
    "--base",
    "-b",
    "base_path",
    default=None,
    help="Path to base resume JSON template",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    default=None,
    help="Path to config file",
)
@click.option(
    "--output",
    "-o",
    default=None,
    help="Path to output JSON file",
)
@click.option(
    "--api-key",
    default=None,
    envvar="RESUME_API_KEY",
    help="Reactive Resume API key (overrides config)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug output with LLM prompts",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force regeneration (ignore cache)",
)
@click.option(
    "--overwrite-resume",
    is_flag=True,
    help="Overwrite existing resume if present",
)
@click.option(
    "--skip-cover-letter",
    is_flag=True,
    help="Skip cover letter generation",
)
@click.option(
    "--base-cover-letter",
    default=None,
    help="Path to base cover letter JSON template",
)
@click.option(
    "--skip-questions",
    is_flag=True,
    help="Skip interactive questions (use cached answers if available)",
)
@click.option(
    "--provider",
    type=click.Choice(["ollama", "opencode-go"]),
    default=None,
    help="LLM provider (overrides config)",
)
@click.option(
    "--no-knowledge",
    is_flag=True,
    help="Disable knowledge features (no fact extraction or injection)",
)
@click.option(
    "--review-facts",
    is_flag=True,
    help="Review extracted facts before storing",
)
def generate(
    url: str | None,
    job_title: str | None,
    content: str | None,
    job_url_opt: str | None,
    profile_path: str | None,
    base_path: str | None,
    config_path: str | None,
    output: str | None,
    api_key: str | None,
    verbose: bool,
    debug: bool,
    force: bool,
    overwrite_resume: bool,
    skip_cover_letter: bool,
    base_cover_letter: str | None,
    skip_questions: bool,
    provider: str | None,
    no_knowledge: bool,
    review_facts: bool,
) -> None:
    """Generate and import resume for a job URL or pasted description.

    \b
    URL mode:  fast-app generate https://example.com/job
    Text mode: fast-app generate --text "Job Title" --content "Job description..."

    When --text and --content are provided, the job description is used
    directly instead of fetching from a URL. Use --job-url to optionally
    store the original URL for metadata.
    """
    from .auth import _get_user_id

    # Validate input mode
    if not url and not (job_title and content):
        raise click.ClickException(
            "Provide a job URL or use --text and --content to paste a job description."
        )
    if url and (job_title or content):
        raise click.ClickException(
            "Cannot use both URL and --text/--content. "
            "Provide either a URL or text input, not both."
        )
    try:
        # Load configuration
        config = load_config(config_path)
        if api_key:
            config.reactive_resume.api_key = api_key

        # Override LLM provider if specified
        if provider:
            config.llm.provider = provider

        # Enable debug logging if requested
        if debug:
            config.ollama.debug = True
            verbose = True

        # Initialize services
        ollama = OllamaService(config.ollama)
        profile = load_profile(profile_path)
        base_resume = load_base_resume(base_path)
        base_cover_letter_data = load_base_cover_letter(base_cover_letter)

        # Check Ollama connection and model availability
        if not ollama.check_connection():
            logger.error(f"Cannot connect to Ollama at {config.ollama.endpoint}")
            raise click.ClickException(f"Cannot connect to Ollama at {config.ollama.endpoint}")

        if not ollama.check_model_available():
            logger.warning(f"Model '{config.ollama.model}' not found")
            if not ollama.ensure_model_available():
                raise click.ClickException(f"Failed to download model '{config.ollama.model}'")

        # Initialize Reactive Resume client
        rr_client = ReactiveResumeClient(
            config.reactive_resume.endpoint, config.reactive_resume.api_key
        )

        # Initialize cache
        output_dir = Path.cwd() / config.output.directory
        cache = CacheManager(output_dir)

        # Initialize callbacks and pipeline
        callbacks = CLICallbacks(verbose=verbose, debug=debug)
        flags = PipelineFlags(
            force=force,
            overwrite_resume=overwrite_resume,
            skip_questions=skip_questions,
            skip_cover_letter=skip_cover_letter,
            no_knowledge=no_knowledge,
            review_facts=review_facts,
            debug=debug,
            verbose=verbose,
        )

        pipeline = PipelineService(
            config=config,
            ollama=ollama,
            cache=cache,
            rr_client=rr_client,
            profile=profile,
            base_resume=base_resume,
            base_cover_letter=base_cover_letter_data,
            callbacks=callbacks,
            user_id=_get_user_id(config_path),
        )

        # Run the pipeline
        result = asyncio.run(
            pipeline.run(
                url=url or "",
                flags=flags,
                job_title_input=job_title,
                content=content,
                job_url_opt=job_url_opt,
            )
        )

        # Handle --output flag
        if output:
            output_path = Path(output)
            output_path.write_text(json.dumps(result.resume_data, indent=2))
            click.echo(f"   Saved JSON to {output}")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise click.ClickException(f"Error: {e}")

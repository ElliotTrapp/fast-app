"""CLI for fast-app."""

import json
from pathlib import Path
from typing import Any

import click

from .config import load_config
from .log import logger
from .services.cache import CacheManager, generate_job_id
from .services.job_extractor import JobExtractor
from .services.ollama import OllamaService
from .services.reactive_resume import ReactiveResumeClient
from .utils import (
    ask_questions_interactive,
    check_existing_cover_letter,
    check_existing_resume,
    find_profile_file,
    load_base_cover_letter,
    load_base_resume,
    load_profile,
    merge_cover_letter_with_base,
    merge_resume_with_base,
    sanitize_name,
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

        # Determine input mode and extract job data
        text_mode = bool(job_title and content)

        if text_mode:
            job_id = generate_job_id(content)
            effective_url = job_url_opt or ""
        else:
            job_id = generate_job_id(url)
            effective_url = url

        # Check if we've already cached this job
        used_cache = False
        job_data = None
        questions = []
        answers = []
        job_dir = None

        if not text_mode:
            existing_job_dir = cache.has_cached_job(url)
            if existing_job_dir and not force:
                used_cache = True
                job_data = cache.get_cached_job(existing_job_dir)
                job_description = job_data.get("description", "")
                raw_title = job_data.get("title", "Unknown")
                raw_company = job_data.get("company", "Unknown")
                job_title = sanitize_name(raw_title)
                company = sanitize_name(raw_company)
                job_dir = existing_job_dir

                logger.cache_hit("job", str(existing_job_dir))
                if verbose and not debug:
                    logger.success("Using cached job data")

                # Check for cached questions/answers
                if not skip_questions:
                    questions_path = existing_job_dir / "questions.json"
                    answers_path = existing_job_dir / "answers.json"

                    if questions_path.exists() and answers_path.exists():
                        questions = cache.get_cached_questions(existing_job_dir) or []
                        answers = cache.get_cached_answers(existing_job_dir) or []
                        logger.cache_hit("questions", str(questions_path))
                        logger.cache_hit("answers", str(answers_path))
                        if verbose and not debug:
                            logger.success("Using cached questions and answers")

        if not used_cache:
            extractor = JobExtractor(ollama.client, config.ollama.model)
            if text_mode:
                job_data = extractor.extract_from_text(job_title, content, url=effective_url)
            else:
                job_data = extractor.extract_from_url(url)

            raw_title = job_data.get("title", "Unknown")
            raw_company = job_data.get("company", "Unknown")
            job_title = sanitize_name(raw_title)
            company = sanitize_name(raw_company)
            job_description = job_data.get("description", "")

            click.echo(f"   Found: {job_title} at {company}")

            logger.detail("job_id", job_id)
            logger.detail("company", company)
            logger.detail("title", job_title)

            job_dir = cache.get_job_dir(company, job_title, job_id, create=True)
            cache.save_job(job_dir, job_data)
            logger.cache_save("job", str(job_dir / "job.json"))
            if verbose and not debug:
                click.echo("   💾 Saved: job.json")

            if not skip_questions:
                questions_path = job_dir / "questions.json"
                answers_path = job_dir / "answers.json"

                if not force and questions_path.exists() and answers_path.exists():
                    questions = cache.get_cached_questions(job_dir) or []
                    answers = cache.get_cached_answers(job_dir) or []
                    logger.cache_hit("questions", str(questions_path))
                    logger.cache_hit("answers", str(answers_path))
                    if verbose and not debug:
                        logger.success("Using cached questions and answers")
                else:
                    knowledge_facts = None
                    if not no_knowledge:
                        try:
                            from .services.knowledge import KnowledgeService

                            knowledge_svc = KnowledgeService(
                                config, user_id=_get_user_id(config_path)
                            )
                            results = knowledge_svc.query_facts(
                                f"{job_data.get('title', '')} "
                                f"{job_data.get('description', '')[:200]}",
                                n=5,
                            )
                            if results:
                                knowledge_facts = [r.content for r in results]
                                logger.info(f"Injected {len(results)} facts from knowledge base")
                        except ImportError:
                            pass
                        except Exception:
                            pass

                    questions = ollama.generate_questions(
                        job_data, profile, knowledge_context=knowledge_facts
                    )
                    if questions:
                        cache.save_questions(job_dir, questions)
                        logger.cache_save("questions", str(questions_path))
                        if verbose and not debug:
                            click.echo("   💾 Saved: questions.json")

                        answers = ask_questions_interactive(questions)
                        cache.save_answers(job_dir, answers)
                        logger.cache_save("answers", str(answers_path))
                        if verbose and not debug:
                            click.echo("   💾 Saved: answers.json")

                        if not no_knowledge and questions and answers:
                            try:
                                from .services.fact_extractor import FactExtractor
                                from .services.knowledge import KnowledgeService
                                from .services.llm_service import LLMService

                                llm_service = LLMService(config)
                                fact_extractor = FactExtractor(llm_service)
                                result = fact_extractor.extract_facts_from_answers(
                                    questions, answers, profile_data=profile, job_data=job_data
                                )
                                if result.facts:
                                    if review_facts:
                                        click.echo("\n📝 Extracted facts:")
                                        for i, fact in enumerate(result.facts, 1):
                                            click.echo(f"  {i}. [{fact.category}] {fact.content}")
                                        if not click.confirm("Store these facts?"):
                                            click.echo("   Skipping fact storage.")
                                            result = None

                                    if result and result.facts:
                                        knowledge_svc = KnowledgeService(
                                            config, user_id=_get_user_id(config_path)
                                        )
                                        stored_ids = knowledge_svc.store_facts(
                                            result.facts, job_url=effective_url or url or ""
                                        )
                                        logger.success(
                                            f"Stored {len(stored_ids)} facts in knowledge base"
                                        )
                            except ImportError:
                                logger.warning(
                                    "Knowledge dependencies not installed, skipping fact extraction"
                                )
                            except Exception as e:
                                logger.warning(f"Fact extraction failed: {e}")
                    else:
                        logger.warning("No questions generated, proceeding with resume creation.")

        # ============================================
        # PHASE 1: Generate all local data first
        # ============================================

        # Generate or load resume content from LLM
        resume_path = job_dir / "resume.json"

        if not force and resume_path.exists():
            resume_data = cache.get_cached_resume(job_dir)
            logger.cache_hit("resume", str(resume_path))
            if verbose and not debug:
                logger.success("Using cached resume data")
        else:
            # Get content from LLM (only summary and sections)
            resume_content = ollama.generate_resume(
                job_data,
                profile,
                questions=questions if questions else None,
                answers=answers if answers else None,
                output_path=str(job_dir / "debug_llm_output.json"),
            )

            # Merge with base template and profile to get full ResumeData
            resume_data = merge_resume_with_base(resume_content, profile, base_resume)

            # Cache the merged result
            cache.save_resume(job_dir, resume_data)
            logger.cache_save("resume", str(resume_path))
            if verbose and not debug:
                click.echo("   💾 Saved: resume.json")

        final_resume = resume_data

        if output:
            output_path = Path(output)
            output_path.write_text(json.dumps(final_resume, indent=2))
            click.echo(f"   Saved JSON to {output}")

        # Generate or load cover letter content from LLM
        cover_letter_data = None

        if not skip_cover_letter:
            base_cl = load_base_cover_letter(base_cover_letter)
            cover_letter_path = job_dir / "cover_letter.json"

            if not force and cover_letter_path.exists():
                cover_letter_data = cache.get_cached_cover_letter(job_dir)
                logger.cache_hit("cover_letter", str(cover_letter_path))
                if verbose and not debug:
                    logger.success("Using cached cover letter data")

            if not cover_letter_data:
                # Get content from LLM (only recipient and content)
                cover_letter_content = ollama.generate_cover_letter(
                    job_data,
                    profile,
                    questions=questions if questions else None,
                    answers=answers if answers else None,
                    output_path=str(job_dir / "debug_cover_letter_output.json"),
                )

                # Merge with base template and profile to get full CoverLetterData
                cover_letter_data = merge_cover_letter_with_base(
                    cover_letter_content, profile, base_cl, job_title, company
                )

                # Cache the merged result
                cache.save_cover_letter(job_dir, cover_letter_data)
                logger.cache_save("cover_letter", str(cover_letter_path))
                if verbose and not debug:
                    click.echo("   💾 Saved: cover_letter.json")

                # Debug: Log the cover letter content
                if debug:
                    content_len = len(cover_letter_content.get("content", ""))
                    click.echo(f"\n📝 Generated cover letter content length: {content_len}")
                    click.echo(f"📝 Cover letter content keys: {list(cover_letter_content.keys())}")

            final_cover_letter = cover_letter_data

            # Debug: Log the merged cover letter
            if debug:
                summary_content = final_cover_letter.get("summary", {}).get("content", "")
                click.echo(
                    f"\n📝 Merged cover letter summary content length: {len(summary_content)}"
                )

        # ============================================
        # PHASE 2: Create/update in Reactive Resume
        # ============================================

        resume_title = f"{job_title} at {company} Resume"

        # Check for existing resume
        existing_resume_id = check_existing_resume(rr_client, cache, job_dir, overwrite_resume)

        if existing_resume_id and not overwrite_resume:
            logger.error(f"Resume '{resume_title}' already exists")
            click.echo(
                click.style(
                    f"\n❌ Error: Resume '{resume_title}' already exists.",
                    fg="red",
                )
            )
            click.echo(
                click.style(
                    "   Use --overwrite-resume to replace it.",
                    fg="yellow",
                )
            )
            raise click.ClickException(
                f"Resume '{resume_title}' already exists. Use --overwrite-resume to overwrite."
            )

        # Add notes with URL and description to resume
        final_resume["metadata"]["notes"] = f"{effective_url}\n\n{job_description}"

        click.echo("\n🚀 Creating resume in Reactive Resume...")

        # Create resume with title and company tag
        resume_id = rr_client.create_resume(resume_title, tags=[company])

        # Update with data
        rr_client.update_resume(resume_id, final_resume)

        # Cache the reactive resume metadata
        cache.save_reactive_resume(
            job_dir,
            {
                "resume_id": resume_id,
                "title": resume_title,
            },
        )
        logger.cache_save("reactive_resume", str(job_dir / "reactive_resume.json"))

        resume_url = rr_client.get_resume_url(resume_id)
        logger.success(f"Resume created: {resume_url}")

        # Create cover letter if requested
        if not skip_cover_letter and final_cover_letter:
            cover_letter_title = f"{job_title} at {company} Cover Letter"

            # Check for existing cover letter using dedicated function
            existing_cl_id = check_existing_cover_letter(
                rr_client, cache, job_dir, overwrite_resume
            )

            if existing_cl_id and not overwrite_resume:
                print("EXISTS")
                logger.error(f"Cover letter '{cover_letter_title}' already exists")
                raise click.ClickException(
                    f"Cover letter '{cover_letter_title}' already exists. "
                    "Use --overwrite-resume to overwrite."
                )

            # Add notes with URL and description to cover letter
            final_cover_letter["metadata"]["notes"] = f"{effective_url}\n\n{job_description}"

            click.echo("\n🚀 Creating cover letter in Reactive Resume...")

            # Create cover letter with unique slug prefix to avoid collision with resume
            cover_letter_id = rr_client.create_resume(
                cover_letter_title, tags=[company], slug_prefix="cl"
            )

            # Update with data
            rr_client.update_resume(cover_letter_id, final_cover_letter)

            # Cache the reactive cover letter metadata
            cache.save_reactive_cover_letter(
                job_dir,
                {
                    "cover_letter_id": cover_letter_id,
                    "title": cover_letter_title,
                },
            )
            logger.cache_save("reactive_cover_letter", str(job_dir / "reactive_cover_letter.json"))

            cover_letter_url = rr_client.get_resume_url(cover_letter_id)
            logger.success(f"Cover letter created: {cover_letter_url}")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise click.ClickException(f"Error: {e}")


@main.command("test-connection")
@click.option(
    "--config",
    "-c",
    "config_path",
    default=None,
    help="Path to config file",
)
@click.option(
    "--api-key",
    default=None,
    envvar="RESUME_API_KEY",
    help="Reactive Resume API key (overrides config)",
)
def test_connection(config_path: str | None, api_key: str | None) -> None:
    """Test connection to Ollama and Reactive Resume."""
    try:
        config = load_config(config_path)
        if api_key:
            config.reactive_resume.api_key = api_key

        click.echo(f"Testing Ollama at {config.ollama.endpoint}...")
        ollama = OllamaService(config.ollama)

        if ollama.check_connection():
            logger.success("Ollama connected")
            if ollama.check_model_available():
                logger.success(f"Model '{config.ollama.model}' available")
            else:
                logger.warning(
                    f"Model '{config.ollama.model}' not available (will download on first run)"
                )
        else:
            logger.error("Cannot connect to Ollama")

        click.echo(f"\nTesting Reactive Resume at {config.reactive_resume.endpoint}...")
        rr_client = ReactiveResumeClient(
            config.reactive_resume.endpoint, config.reactive_resume.api_key
        )

        if rr_client.test_connection():
            logger.success("Reactive Resume connected")
            if config.reactive_resume.api_key:
                logger.success("API key configured")
            else:
                logger.warning("No API key configured (set in config or via --api-key)")
        else:
            logger.error("Cannot connect to Reactive Resume")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(str(e))
        raise click.ClickException(str(e))


@main.command("list")
@click.option(
    "--config",
    "-c",
    "config_path",
    default=None,
    help="Path to config file",
)
@click.option(
    "--company",
    "-co",
    default=None,
    help="Filter by company name",
)
@click.option(
    "--recent",
    "-r",
    default=None,
    type=int,
    help="Show only N most recent jobs",
)
def list_jobs(config_path: str | None, company: str | None, recent: int | None) -> None:
    """List cached job applications.

    Shows company, title, and status for each cached job.
    """
    try:
        config = load_config(config_path)
        output_dir = Path.cwd() / config.output.directory

        if not output_dir.exists():
            click.echo("No cached jobs found.")
            return

        cache = CacheManager(output_dir)

        jobs: list[dict[str, Any]] = []

        for company_dir in sorted(output_dir.iterdir()):
            if not company_dir.is_dir():
                continue

            if company and company.lower() not in company_dir.name.lower():
                continue

            for title_dir in company_dir.iterdir():
                if not title_dir.is_dir():
                    continue

                for job_id_dir in title_dir.iterdir():
                    if not job_id_dir.is_dir():
                        continue

                    job_data = cache.get_cached_job(job_id_dir)
                    if not job_data:
                        continue

                    has_resume = (job_id_dir / "resume.json").exists()
                    has_cover_letter = (job_id_dir / "cover_letter.json").exists()
                    has_reactive_resume = (job_id_dir / "reactive_resume.json").exists()

                    jobs.append(
                        {
                            "company": company_dir.name,
                            "title": title_dir.name.replace("-", " "),
                            "job_id": job_id_dir.name,
                            "has_resume": has_resume,
                            "has_cover_letter": has_cover_letter,
                            "has_reactive_resume": has_reactive_resume,
                            "path": job_id_dir,
                        }
                    )

        if not jobs:
            click.echo("No cached jobs found.")
            return

        if recent:
            jobs = jobs[-recent:]

        click.echo(f"\n📋 Found {len(jobs)} cached job(s):\n")
        click.echo(f"{'Company':<30} {'Title':<35} {'Status'}")
        click.echo("─" * 80)

        for job in jobs:
            status_parts = []
            if job["has_reactive_resume"]:
                status_parts.append("✓ Published")
            elif job["has_resume"]:
                status_parts.append("○ Generated")
            else:
                status_parts.append("○ Extracted")

            if job["has_cover_letter"]:
                status_parts.append("+ Cover Letter")

            status = " | ".join(status_parts)
            click.echo(f"{job['company']:<30} {job['title']:<35} {status}")

        click.echo()

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        raise click.ClickException(f"Error listing jobs: {e}")


@main.command("status")
@click.option(
    "--config",
    "-c",
    "config_path",
    default=None,
    help="Path to config file",
)
def status_command(config_path: str | None) -> None:
    """Show status of dependencies.

    Checks:
    - Configuration file
    - Profile file
    - Ollama connection
    - Reactive Resume connection
    - Model availability
    """
    try:
        click.echo("\n📊 Fast App Status\n")

        config_status: list[str] = []
        config_ok = True
        try:
            config = load_config(config_path)
            config_status.append("✓ Config file found")
            config_status.append(f"  Endpoint: {config.ollama.endpoint}")
            config_status.append(f"  Model: {config.ollama.model}")
            if config.ollama.cloud:
                config_status.append(
                    f"  Mode: Cloud (API key: {'✓' if config.ollama.api_key else '✗'})"
                )
            else:
                config_status.append("  Mode: Local")
        except FileNotFoundError:
            config_status.append("✗ Config file not found")
            config_ok = False

        profile_status: list[str] = []
        profile_ok = True
        try:
            profile_path = find_profile_file(None)
            profile_status.append(f"✓ Profile file found: {profile_path}")
        except FileNotFoundError:
            profile_status.append("✗ Profile file not found")
            profile_ok = False

        ollama_status: list[str] = []
        ollama_ok = True
        try:
            config = load_config(config_path)
            ollama = OllamaService(config.ollama)
            if ollama.check_connection():
                ollama_status.append("✓ Ollama connection")
                if ollama.check_model_available():
                    ollama_status.append(f"  Model '{config.ollama.model}' available")
                else:
                    ollama_status.append(f"  ⚠ Model '{config.ollama.model}' not downloaded")
                    ollama_status.append(f"    Run: ollama pull {config.ollama.model}")
            else:
                ollama_status.append("✗ Ollama connection failed")
                ollama_ok = False
        except Exception as e:
            ollama_status.append(f"✗ Ollama check failed: {e}")
            ollama_ok = False

        rr_status: list[str] = []
        rr_ok = True
        try:
            config = load_config(config_path)
            if config.reactive_resume.api_key:
                rr = ReactiveResumeClient(
                    config.reactive_resume.endpoint, config.reactive_resume.api_key
                )
                if rr.test_connection():
                    rr_status.append(
                        f"✓ Reactive Resume connection ({config.reactive_resume.endpoint})"
                    )
                    rr_status.append("  API key configured")
                else:
                    rr_status.append("✗ Reactive Resume connection failed")
                    rr_ok = False
            else:
                rr_status.append("⚠ Reactive Resume: No API key configured")
                rr_ok = False
        except FileNotFoundError:
            rr_status.append("✗ Config not found - cannot check Reactive Resume")
            rr_ok = False
        except Exception as e:
            rr_status.append(f"✗ Reactive Resume check failed: {e}")
            rr_ok = False

        click.echo("Configuration:")
        for line in config_status:
            click.echo(f"  {line}")
        click.echo()

        click.echo("Profile:")
        for line in profile_status:
            click.echo(f"  {line}")
        click.echo()

        click.echo("Ollama:")
        for line in ollama_status:
            click.echo(f"  {line}")
        click.echo()

        click.echo("Reactive Resume:")
        for line in rr_status:
            click.echo(f"  {line}")
        click.echo()

        all_ok = config_ok and profile_ok and ollama_ok and rr_ok
        if all_ok:
            click.echo(click.style("✓ All checks passed!", fg="green", bold=True))
        else:
            click.echo(click.style("⚠ Some checks failed. See details above.", fg="yellow"))

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error checking status: {e}")
        raise click.ClickException(f"Error checking status: {e}")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--config", "-c", default=None, help="Config file path")
def serve(host: str, port: int, config: str | None) -> None:
    """Start Fast-App web server.

    Launches a web interface for generating resumes.
    Checks connections and configuration before starting.
    """
    from pathlib import Path

    import uvicorn

    try:
        # Load configuration
        config_obj = load_config(config)

        # Validate connections
        click.echo("🔍 Validating connections...\n")

        # Check Ollama
        ollama = OllamaService(config_obj.ollama)
        click.echo("Checking Ollama...")
        if not ollama.check_connection():
            click.echo(click.style("❌ Cannot connect to Ollama", fg="red"))
            click.echo(f"   Ensure Ollama is running at: {config_obj.ollama.endpoint}")
            raise SystemExit(1)
        click.echo(click.style(f"✅ Ollama connected ({config_obj.ollama.endpoint})", fg="green"))

        if not ollama.check_model_available():
            click.echo(f"⚠️  Model '{config_obj.ollama.model}' not available")
            click.echo(f"   Run: ollama pull {config_obj.ollama.model}")
        else:
            click.echo(f"✅ Model '{config_obj.ollama.model}' available")

        click.echo()

        # Check Reactive Resume
        rr_client = ReactiveResumeClient(config_obj.resume.endpoint, config_obj.resume.api_key)
        click.echo("Checking Reactive Resume...")
        if not rr_client.test_connection():
            click.echo(click.style("❌ Cannot connect to Reactive Resume", fg="red"))
            click.echo(f"   Ensure Reactive Resume is running at: {config_obj.resume.endpoint}")
            raise SystemExit(1)
        click.echo(
            click.style(f"✅ Reactive Resume connected ({config_obj.resume.endpoint})", fg="green")
        )

        if not config_obj.resume.api_key:
            click.echo("⚠️  No API key configured")
            click.echo("   Set RESUME_API_KEY environment variable or add to config.json")
        else:
            click.echo("✅ API key configured")

        click.echo()

        # Check required files
        click.echo("Checking configuration files...")

        required_files = [
            ("config.json", config),
            ("profile.json", None),
            ("base-resume.json", None),
            ("base-cover-letter.json", None),
        ]

        for filename, custom_path in required_files:
            file_path = Path(custom_path) if custom_path else Path(filename)
            if not file_path.exists():
                click.echo(click.style(f"❌ Missing {filename}", fg="red"))
                click.echo(f"   Create {filename} in the current directory")
                raise SystemExit(1)
            click.echo(f"✅ Found {filename}")

        click.echo()
        click.echo(click.style("=" * 60, fg="cyan"))
        click.echo(click.style("🚀 Fast-App server starting", fg="green", bold=True))
        click.echo(click.style(f"   http://{host}:{port}", fg="cyan"))
        click.echo(click.style("=" * 60, fg="cyan"))
        click.echo()

        # Import and run app
        from .webapp.app import app as webapp

        # Configure uvicorn
        uvicorn.run(webapp, host=host, port=port, log_level="info", access_log=False)

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise click.ClickException(f"Server error: {e}")


# ── Auth command group ──────────────────────────────────────────────────────


@main.group()
def auth():
    """Authentication commands (signup, login, logout, whoami)."""
    pass


@auth.command()
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--password", "-p", required=True, help="Password", hide_input=True)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def signup(email: str, password: str, config_path: str | None) -> None:
    """Create a new user account.

    Creates a user with the given email and password, then
    stores the authentication token for CLI use.
    """
    try:
        from ..db import get_session, init_db
        from ..models.db_models import User
        from ..services.auth import create_access_token, hash_password

        init_db()
        session = next(get_session())

        existing = session.exec(
            __import__("sqlmodel").select(User).where(User.email == email)
        ).first()
        if existing:
            raise click.ClickException(f"Email '{email}' is already registered")

        user = User(email=email, hashed_password=hash_password(password))
        session.add(user)
        session.commit()
        session.refresh(user)

        token = create_access_token(user.id)

        _save_token(token)
        click.echo(click.style(f"✓ Account created for {email}", fg="green"))
        click.echo(click.style("  Token saved. You are now logged in.", fg="green"))
    except ValueError as e:
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise click.ClickException(f"Signup failed: {e}")


@auth.command()
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--password", "-p", required=True, help="Password", hide_input=True)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def login(email: str, password: str, config_path: str | None) -> None:
    """Log in with email and password.

    Authenticates and stores the token for subsequent CLI commands.
    """
    try:
        from sqlmodel import select

        from ..db import get_session, init_db
        from ..models.db_models import User
        from ..services.auth import create_access_token, hash_password, verify_password

        init_db()
        session = next(get_session())

        user = session.exec(select(User).where(User.email == email)).first()

        if user is None:
            hash_password(password)  # Prevent timing attack
            raise click.ClickException("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise click.ClickException("Invalid email or password")

        if not user.is_active:
            raise click.ClickException("Account is deactivated")

        token = create_access_token(user.id)

        _save_token(token)
        click.echo(click.style(f"✓ Logged in as {email}", fg="green"))
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise click.ClickException(f"Login failed: {e}")


@auth.command()
def whoami() -> None:
    """Show the currently authenticated user."""
    try:
        from ..db import get_session
        from ..models.db_models import User
        from ..services.auth import decode_access_token

        token = _load_token()
        if not token:
            raise click.ClickException("Not logged in. Run 'fast-app auth login' first.")

        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))

        session = next(get_session())
        user = session.get(User, user_id)

        if user is None:
            raise click.ClickException("User not found. Token may be invalid.")

        click.echo(f"Email:     {user.email}")
        click.echo(f"User ID:   {user.id}")
        click.echo(f"Active:    {user.is_active}")
        click.echo(f"Created:   {user.created_at}")
    except ValueError as e:
        raise click.ClickException(f"Authentication error: {e}")
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Whoami error: {e}")
        raise click.ClickException(f"Whoami failed: {e}")


@auth.command()
def logout() -> None:
    """Log out by removing the stored token."""
    _remove_token()
    click.echo(click.style("✓ Logged out", fg="green"))


def _token_path() -> Path:
    """Get the path to the auth token file."""
    xdg_data = __import__("os").environ.get("XDG_DATA_HOME", "~/.local/share")
    token_dir = Path(xdg_data).expanduser() / "fast-app"
    token_dir.mkdir(parents=True, exist_ok=True)
    return token_dir / "auth.json"


def _save_token(token: str) -> None:
    """Save the auth token to disk."""
    token_path = _token_path()
    token_path.write_text(json.dumps({"access_token": token}))
    token_path.chmod(0o600)


def _load_token() -> str | None:
    """Load the auth token from disk. Returns None if not found."""
    token_path = _token_path()
    if not token_path.exists():
        return None
    try:
        data = json.loads(token_path.read_text())
        return data.get("access_token")
    except (json.JSONDecodeError, KeyError):
        return None


def _remove_token() -> None:
    """Remove the auth token from disk."""
    token_path = _token_path()
    if token_path.exists():
        token_path.unlink()


def _get_user_id(config_path: str | None) -> int:
    """Get the current user ID from the stored auth token.

    Falls back to user_id=1 when auth is disabled (no token or no JWT secret).
    """
    token = _load_token()
    if token:
        try:
            from .services.auth import JWT_SECRET, decode_access_token

            if JWT_SECRET:
                payload = decode_access_token(token)
                return int(payload.get("sub", 1))
        except Exception:
            pass
    return 1


# ── Profile command group ────────────────────────────────────────────────────


@main.group()
def profile():
    """Profile management commands (list, import, export, set-default, delete)."""
    pass


@profile.command("list")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_list(config_path: str | None) -> None:
    """List all profiles for the current user."""
    try:
        from .db import get_session, init_db
        from .services.profile_service import ProfileService

        init_db()
        session = next(get_session())
        user_id = _get_user_id(config_path)
        service = ProfileService()
        profiles = service.list_profiles(user_id=user_id, session=session)

        if not profiles:
            click.echo("No profiles found.")
            return

        click.echo(f"\n📋 Profiles for user {user_id}:\n")
        click.echo(f"  {'ID':<6} {'Name':<25} {'Default':<10} {'Created'}")
        click.echo("  " + "─" * 70)

        for p in profiles:
            default_marker = "✓" if p.is_default else ""
            click.echo(f"  {p.id:<6} {p.name:<25} {default_marker:<10} {p.created_at}")

        click.echo()

    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[auth]'"
        )
    except Exception as e:
        logger.error(f"Error listing profiles: {e}")
        raise click.ClickException(f"Error listing profiles: {e}")


@profile.command("import")
@click.argument("path", type=click.Path(exists=True))
@click.option("--name", "-n", default="Imported", help="Profile name (default: Imported)")
@click.option("--default", "is_default", is_flag=True, help="Set as default profile")
@click.option("--extract-facts", is_flag=True, help="Extract knowledge facts from imported profile")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_import(
    path: str, name: str, is_default: bool, extract_facts: bool, config_path: str | None
) -> None:
    """Import a profile from a JSON file.

    \b
    PATH  Path to the profile JSON file to import.

    Use --extract-facts to distill the profile into knowledge facts
    stored in ChromaDB for use in future question generation.
    """
    try:
        from .db import get_session, init_db
        from .services.profile_service import ProfileService

        init_db()
        session = next(get_session())
        user_id = _get_user_id(config_path)
        service = ProfileService()

        result = service.import_profile(
            file_path=path,
            user_id=user_id,
            session=session,
            name=name,
            is_default=is_default,
        )

        click.echo(click.style(f"✓ Imported profile '{result.name}' (ID: {result.id})", fg="green"))
        if is_default:
            click.echo(click.style("  Set as default profile", fg="green"))

        if extract_facts:
            try:
                from .services.fact_extractor import FactExtractor
                from .services.knowledge import KnowledgeService
                from .services.llm_service import LLMService

                config = load_config(config_path)
                llm_service = LLMService(config)
                extractor = FactExtractor(llm_service)

                profile_dict = json.loads(result.profile_data)

                provider_name = config.llm.provider
                click.echo(f"  Extracting facts via {provider_name} (this may take a minute)...")

                extraction = extractor.extract_facts_from_profile(profile_dict)

                if extraction.facts:
                    knowledge_svc = KnowledgeService(config, user_id=user_id)
                    stored_ids = knowledge_svc.store_facts(
                        extraction.facts,
                        source="profile_import",
                    )
                    click.echo(
                        click.style(
                            f"  Extracted and stored {len(stored_ids)} facts from profile",
                            fg="green",
                        )
                    )
                else:
                    click.echo("  No extractable facts found in profile")

            except ImportError:
                click.echo(
                    click.style(
                        "  Skipping fact extraction: knowledge deps not installed. "
                        "Install with: pip install -e '.[knowledge,llm]'",
                        fg="yellow",
                    )
                )
            except Exception as e:
                logger.error(f"Error extracting facts from profile: {e}")
                click.echo(click.style(f"  Warning: fact extraction failed: {e}", fg="yellow"))

    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON file: {e}")
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[auth]'"
        )
    except Exception as e:
        logger.error(f"Error importing profile: {e}")
        raise click.ClickException(f"Error importing profile: {e}")


@profile.command("export")
@click.option("--id", "profile_id", type=int, default=None, help="Profile ID (default: default)")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout)")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_export(profile_id: int | None, output: str | None, config_path: str | None) -> None:
    """Export a profile as JSON.

    Exports the default profile unless --id is specified.
    """
    try:
        from .db import get_session, init_db
        from .services.profile_service import ProfileService

        init_db()
        session = next(get_session())
        user_id = _get_user_id(config_path)
        service = ProfileService()

        if profile_id is None:
            default = service.get_default_profile(user_id=user_id, session=session)
            if default is None:
                raise click.ClickException(
                    "No default profile found. Specify --id to export a specific profile."
                )
            profile_id = default.id

        result = service.export_profile(profile_id=profile_id, user_id=user_id, session=session)

        if result is None:
            raise click.ClickException(f"Profile {profile_id} not found or not owned by you.")

        json_output = json.dumps(result, indent=2, default=str)

        if output:
            Path(output).write_text(json_output)
            click.echo(click.style(f"✓ Profile exported to {output}", fg="green"))
        else:
            click.echo(json_output)

    except click.ClickException:
        raise
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[auth]'"
        )
    except Exception as e:
        logger.error(f"Error exporting profile: {e}")
        raise click.ClickException(f"Error exporting profile: {e}")


@profile.command("set-default")
@click.argument("profile_id", type=int)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_set_default(profile_id: int, config_path: str | None) -> None:
    """Set a profile as the default.

    \b
    PROFILE_ID  The ID of the profile to set as default.
    """
    try:
        from .db import get_session, init_db
        from .models.db_models import ProfileCreate
        from .services.profile_service import ProfileService

        init_db()
        session = next(get_session())
        user_id = _get_user_id(config_path)
        service = ProfileService()

        existing = service.get_profile(profile_id, user_id=user_id, session=session)
        if existing is None:
            raise click.ClickException(f"Profile {profile_id} not found or not owned by you.")

        data = ProfileCreate(
            name=existing.name,
            profile_data=json.loads(existing.profile_data),
            is_default=True,
        )
        updated = service.update_profile(
            profile_id=profile_id, user_id=user_id, data=data, session=session
        )

        if updated is None:
            raise click.ClickException(f"Failed to set profile {profile_id} as default.")

        click.echo(
            click.style(f"✓ Profile '{updated.name}' (ID: {updated.id}) set as default", fg="green")
        )

    except click.ClickException:
        raise
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[auth]'"
        )
    except Exception as e:
        logger.error(f"Error setting default profile: {e}")
        raise click.ClickException(f"Error setting default profile: {e}")


@profile.command("delete")
@click.argument("profile_id", type=int)
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_delete(profile_id: int, config_path: str | None) -> None:
    """Delete a profile by ID.

    \b
    PROFILE_ID  The ID of the profile to delete.
    """
    try:
        from .db import get_session, init_db
        from .services.profile_service import ProfileService

        init_db()
        session = next(get_session())
        user_id = _get_user_id(config_path)
        service = ProfileService()

        deleted = service.delete_profile(profile_id=profile_id, user_id=user_id, session=session)

        if not deleted:
            raise click.ClickException(f"Profile {profile_id} not found or not owned by you.")

        click.echo(click.style(f"✓ Profile {profile_id} deleted", fg="green"))

    except click.ClickException:
        raise
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[auth]'"
        )
    except Exception as e:
        logger.error(f"Error deleting profile: {e}")
        raise click.ClickException(f"Error deleting profile: {e}")


# ── Knowledge command group ──────────────────────────────────────────────────


@main.group()
def knowledge():
    """Knowledge management commands (search, list, delete)."""
    pass


@knowledge.command("search")
@click.argument("query")
@click.option("-n", "--num-results", default=5, type=int, help="Number of results (default: 5)")
@click.option("--category", default=None, help="Filter by category (skill, experience, etc.)")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def knowledge_search(
    query: str, num_results: int, category: str | None, config_path: str | None
) -> None:
    """Search knowledge facts by query.

    \b
    QUERY  Natural language search string.

    \b
    Examples:
      fast-app knowledge search "python experience"
      fast-app knowledge search "leadership" --category experience
      fast-app knowledge search "distributed systems" -n 10
    """
    try:
        from .services.knowledge import KnowledgeService

        config = load_config(config_path)
        user_id = _get_user_id(config_path)
        service = KnowledgeService(config, user_id=user_id)

        results = service.query_facts(query=query, n=num_results, category=category)

        if not results:
            click.echo("No matching facts found.")
            return

        click.echo(f"\n🔍 Search results for '{query}':\n")
        for i, result in enumerate(results, 1):
            distance_str = f" (distance: {result.distance:.4f})" if result.distance else ""
            click.echo(f"  {i}. [{result.category}] {result.content}{distance_str}")
            click.echo(f"     ID: {result.id}")
            if result.source:
                click.echo(f"     Source: {result.source}")
            if result.confidence:
                click.echo(f"     Confidence: {result.confidence:.2f}")
            click.echo()

    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[knowledge]'"
        )
    except Exception as e:
        logger.error(f"Error searching knowledge: {e}")
        raise click.ClickException(f"Error searching knowledge: {e}")


@knowledge.command("list")
@click.option("--category", default=None, help="Filter by category (skill, experience, etc.)")
@click.option("--limit", default=100, type=int, help="Maximum number of facts to list")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def knowledge_list(category: str | None, limit: int, config_path: str | None) -> None:
    """List stored knowledge facts, optionally filtered by category."""
    try:
        from .services.knowledge import KnowledgeService

        config = load_config(config_path)
        user_id = _get_user_id(config_path)
        service = KnowledgeService(config, user_id=user_id)

        facts = service.list_facts(limit=limit, category=category)

        if not facts:
            category_msg = f" in category '{category}'" if category else ""
            click.echo(f"No knowledge facts found{category_msg}.")
            return

        category_msg = f" in category '{category}'" if category else ""
        click.echo(f"\n📚 Knowledge facts{category_msg} ({len(facts)} total):\n")

        for i, fact in enumerate(facts, 1):
            click.echo(f"  {i}. [{fact.category}] {fact.content}")
            click.echo(f"     ID: {fact.id}")
            if fact.source:
                click.echo(f"     Source: {fact.source}")
            if fact.confidence:
                click.echo(f"     Confidence: {fact.confidence:.2f}")
            click.echo()

    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[knowledge]'"
        )
    except Exception as e:
        logger.error(f"Error listing knowledge: {e}")
        raise click.ClickException(f"Error listing knowledge: {e}")


@knowledge.command("delete")
@click.argument("ids")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def knowledge_delete(ids: str, config_path: str | None) -> None:
    """Delete knowledge facts by comma-separated IDs.

    Use the ID shown by 'fast-app knowledge list' (UUID).

    \b
    IDS  Comma-separated list of fact IDs to delete.

    \b
    Examples:
      fast-app knowledge delete a1b2c3d4-e5f6-7890-abcd-ef1234567890
      fast-app knowledge delete id1,id2,id3
    """
    try:
        from .services.knowledge import KnowledgeService

        config = load_config(config_path)
        user_id = _get_user_id(config_path)
        service = KnowledgeService(config, user_id=user_id)

        fact_ids = [id.strip() for id in ids.split(",") if id.strip()]

        if not fact_ids:
            raise click.ClickException("No IDs provided. Use comma-separated IDs.")

        success = service.delete_facts(fact_ids)

        if success:
            click.echo(click.style(f"✓ Deleted {len(fact_ids)} fact(s)", fg="green"))
        else:
            raise click.ClickException("Failed to delete facts. ChromaDB may be unavailable.")

    except click.ClickException:
        raise
    except ImportError as e:
        raise click.ClickException(
            f"Missing dependency: {e}. Install with: pip install -e '.[knowledge]'"
        )
    except Exception as e:
        logger.error(f"Error deleting knowledge: {e}")
        raise click.ClickException(f"Error deleting knowledge: {e}")


if __name__ == "__main__":
    main()

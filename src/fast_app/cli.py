"""CLI for fast-app."""

import json
from pathlib import Path

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
@click.argument("url")
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
def generate(
    url: str,
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
) -> None:
    """Generate and import resume for job URL.

    Generates a tailored resume and cover letter for the given job URL.
    Creates Reactive Resume entries via API.
    """
    try:
        # Load configuration
        config = load_config(config_path)
        if api_key:
            config.resume.api_key = api_key

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
        rr_client = ReactiveResumeClient(config.resume.endpoint, config.resume.api_key)

        # Initialize cache
        output_dir = Path.cwd() / config.output.directory

        # Extract job ID from URL hash
        job_id = generate_job_id(url)

        # Check if we've already cached this job
        used_cache = False
        job_data = None
        questions = []
        answers = []
        job_dir = None
        cache = CacheManager(output_dir)

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
            job_data = JobExtractor(ollama.client, config.ollama.model).extract_from_url(url)
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
                    questions = ollama.generate_questions(job_data, profile)
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
                    else:
                        logger.warning("No questions generated, proceeding with resume creation.")

        # ============================================
        # PHASE 1: Generate all local data first
        # ============================================

        # Generate or load resume data
        resume_path = job_dir / "resume.json"

        if not force and resume_path.exists():
            resume_data = cache.get_cached_resume(job_dir)
            logger.cache_hit("resume", str(resume_path))
            if verbose and not debug:
                logger.success("Using cached resume data")
        else:
            resume_data = ollama.generate_resume(
                job_data,
                profile,
                questions=questions if questions else None,
                answers=answers if answers else None,
                output_path=str(job_dir / "debug_llm_output.json"),
            )
            cache.save_resume(job_dir, resume_data)
            logger.cache_save("resume", str(resume_path))
            if verbose and not debug:
                click.echo("   💾 Saved: resume.json")

        final_resume = merge_resume_with_base(resume_data, base_resume)

        if output:
            output_path = Path(output)
            output_path.write_text(json.dumps(final_resume, indent=2))
            click.echo(f"   Saved JSON to {output}")

        # Generate or load cover letter data
        cover_letter_data = None
        final_cover_letter = None

        if not skip_cover_letter:
            base_cl = load_base_cover_letter(base_cover_letter)
            cover_letter_path = job_dir / "cover_letter.json"

            if not force and cover_letter_path.exists():
                cover_letter_data = cache.get_cached_cover_letter(job_dir)
                logger.cache_hit("cover_letter", str(cover_letter_path))
                if verbose and not debug:
                    logger.success("Using cached cover letter data")

            if not cover_letter_data:
                cover_letter_data = ollama.generate_cover_letter(
                    job_data,
                    profile,
                    questions=questions if questions else None,
                    answers=answers if answers else None,
                    output_path=str(job_dir / "debug_cover_letter_output.json"),
                )
                cache.save_cover_letter(job_dir, cover_letter_data)
                logger.cache_save("cover_letter", str(cover_letter_path))
                if verbose and not debug:
                    click.echo("   💾 Saved: cover_letter.json")

                # Debug: Log the cover letter content
                if debug:
                    click.echo(
                        f"\n📝 Generated cover letter content length: {len(cover_letter_data.get('content', ''))}"
                    )
                    click.echo(f"📝 Cover letter keys: {list(cover_letter_data.keys())}")

            final_cover_letter = merge_cover_letter_with_base(
                cover_letter_data, profile, base_cl, job_title, company
            )

            # Debug: Log the merged cover letter
            if debug:
                click.echo(
                    f"\n📝 Merged cover letter summary content length: {len(final_cover_letter.get('summary', {}).get('content', ''))}"
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
        final_resume["metadata"]["notes"] = f"{url}\n\n{job_description}"

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
                print(f"EXISTS")
                logger.error(f"Cover letter '{cover_letter_title}' already exists")
                raise click.ClickException(
                    f"Cover letter '{cover_letter_title}' already exists. "
                    "Use --overwrite-resume to overwrite."
                )

            # Add notes with URL and description to cover letter
            final_cover_letter["metadata"]["notes"] = f"{url}\n\n{job_description}"

            # Debug: Log what we're about to upload
            if debug:
                import json

                click.echo("\n📝 Final cover letter structure:")
                click.echo(json.dumps(final_cover_letter.get("summary", {}), indent=2)[:500])

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
            config.resume.api_key = api_key

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

        click.echo(f"\nTesting Reactive Resume at {config.resume.endpoint}...")
        rr_client = ReactiveResumeClient(config.resume.endpoint, config.resume.api_key)

        if rr_client.test_connection():
            logger.success("Reactive Resume connected")
            if config.resume.api_key:
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

        jobs: list[dict[str, any]] = []

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
            if config.resume.api_key:
                rr = ReactiveResumeClient(config.resume.endpoint, config.resume.api_key)
                if rr.test_connection():
                    rr_status.append(f"✓ Reactive Resume connection ({config.resume.endpoint})")
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


if __name__ == "__main__":
    main()

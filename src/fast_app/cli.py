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

        # Initialize knowledge base (global location)
        from pathlib import Path as PathlibPath
        from .knowledge import KnowledgeBase

        kb_dir = PathlibPath.home() / ".fast-app"
        kb_dir.mkdir(exist_ok=True)
        kb_path = kb_dir / "knowledge.db"

        kb = KnowledgeBase(str(kb_path))

        if debug:
            click.echo(f"\n📚 Knowledge base: {kb_path}")

        if verbose:
            stats = kb.get_stats()
            if stats["total_facts"] > 0:
                click.echo(f"   ✓ Knowledge base: {stats['total_facts']} facts")
                if debug:
                    click.echo(f"      By type: {stats['facts_by_type']}")
                    click.echo(f"      By source: {stats['facts_by_source']}")
                    if stats["facts_needing_refresh"] > 0:
                        click.echo(f"      ⚠️  {stats['facts_needing_refresh']} facts need refresh")
            else:
                click.echo(f"   ✓ Knowledge base: empty (will learn from Q&A)")

        # ============================================
        # JOB EXTRACTION
        # ============================================
        # KNOWLEDGE BASE INITIALIZATION
        # ============================================

        kb_path = output_dir / "knowledge.db"
        # kb_path = Path(Path(__file__).parent.parent.parent, "knowledge.db")
        kb = None

        if kb_path.exists():
            from .knowledge import KnowledgeBase

            if debug:
                click.echo("\n📚 Loading knowledge base...")

            kb = KnowledgeBase(str(kb_path))
            stats = kb.get_stats()

            if verbose:
                click.echo(f"   ✓ Knowledge base loaded: {stats['total_facts']} facts")
                click.echo(f"   ✓ Facts by type: {stats['facts_by_type']}")
                click.echo(f"   ✓ Facts by source: {stats['facts_by_source']}")

                if stats["total_facts"] > 0:
                    if stats["facts_needing_refresh"] > 0:
                        click.echo(f"   ⚠️  {stats['facts_needing_refresh']} facts need refresh")
                    click.echo(f"   ✓ Average confidence: {stats.get('average_confidence', 0):.0%}")
        else:
            if debug:
                click.echo("\n📚 No knowledge base found, will create after Q&A")

        # ============================================
        # JOB EXTRACTION
        # ============================================

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
        # KNOWLEDGE BASE: Extract facts from Q&A
        # ============================================

        if answers and not skip_questions:
            from .knowledge.integration import extract_facts_from_qa

            fact_ids = extract_facts_from_qa(questions, answers, kb, debug=debug)

            if verbose and fact_ids:
                click.echo(f"   ✓ Extracted {len(fact_ids)} facts from Q&A")

        # ============================================
        # KNOWLEDGE BASE: Get relevant context
        # ============================================

        kb_context = None
        from .knowledge.integration import get_relevant_context

        kb_context = get_relevant_context(kb, job_data, debug=debug)

        if verbose and kb_context:
            click.echo(f"   ✓ Found {len(kb_context)} relevant facts in KB")

            if debug:
                # Show facts by type
                by_type = {}
                for item in kb_context:
                    fact_type = item["fact"]["type"]
                    by_type[fact_type] = by_type.get(fact_type, 0) + 1
                click.echo(f"      By type: {by_type}")

        # ============================================
        # PHASE 1: Generate all local data first
        # ============================================

        kb_context = None
        if kb:
            from .knowledge.integration import get_relevant_context, format_context_for_prompt

            kb_context = get_relevant_context(kb, job_data, debug=debug)

            if verbose and kb_context:
                click.echo(f"   ✓ Found {len(kb_context)} relevant facts in KB")

                if debug:
                    # Show facts by type
                    by_type = {}
                    for item in kb_context:
                        fact_type = item["fact"]["type"]
                        by_type[fact_type] = by_type.get(fact_type, 0) + 1
                    click.echo(f"      By type: {by_type}")

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
                    click.echo(
                        f"\n📝 Generated cover letter content length: {len(cover_letter_content.get('content', ''))}"
                    )
                    click.echo(f"📝 Cover letter content keys: {list(cover_letter_content.keys())}")

            final_cover_letter = cover_letter_data

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

        # ============================================
        # KNOWLEDGE BASE: Record generation
        # ============================================

        from .knowledge.integration import record_generation

        generation_id = record_generation(
            kb=kb,
            job_url=url,
            job_title=job_title,
            company=company,
            related_facts=[item["fact"]["id"] for item in kb_context] if kb_context else None,
            debug=debug,
        )

        if verbose:
            click.echo(f"   ✓ Recorded generation in KB: {generation_id[:8]}")

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

        # ============================================
        # KNOWLEDGE BASE: Summary
        # ============================================

        if verbose:
            click.echo("\n📚 Knowledge Base Summary:")
            from .knowledge.integration import summarize_knowledge_base

            summary = summarize_knowledge_base(kb)
            click.echo(f"   Total facts: {summary['total_facts']}")
            click.echo(f"   Health score: {summary['health_score']:.0%}")
            click.echo(
                f"   Generations: {summary['total_generations']} ({summary['successful_generations']} successful)"
            )
            click.echo(f"   Location: {kb_path}")

            if summary["needing_refresh"] > 0:
                click.echo(f"   ⚠️  {summary['needing_refresh']} facts need refresh")
                click.echo("      Run 'harlequin ~/.fast-app/knowledge.db' to explore and update")

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


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--config", "-c", default=None, help="Config file path")
def serve(host: str, port: int, config: str | None) -> None:
    """Start Fast-App web server.

    Launches a web interface for generating resumes.
    Checks connections and configuration before starting.
    """
    import uvicorn
    from pathlib import Path

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
        click.echo(click.style(f"🚀 Fast-App server starting", fg="green", bold=True))
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


@main.group()
def profile() -> None:
    """Manage knowledge base profile (facts about user).

    Use 'harlequin ~/.fast-app/knowledge.db' to explore the database interactively.
    """
    click.echo("Use 'harlequin ~/.fast-app/knowledge.db' to explore the knowledge base.")
    click.echo("\nSubcommands:")
    click.echo("  show  - Show statistics")
    click.echo("  dump  - Export to JSON")
    click.echo("  load  - Import from JSON")


@profile.command()
def show() -> None:
    """Show knowledge base statistics."""
    from pathlib import Path as PathlibPath
    from .knowledge import KnowledgeBase

    try:
        kb_dir = PathlibPath.home() / ".fast-app"
        kb_path = kb_dir / "knowledge.db"

        if not kb_path.exists():
            click.echo("\n⚠️  Knowledge base not found.")
            click.echo(f"   Expected at: {kb_path}")
            click.echo(
                "   Run 'fast-app generate <url>' to create and populate the knowledge base."
            )
            return

        kb = KnowledgeBase(str(kb_path))
        stats = kb.get_stats()

        click.echo("\n📊 Knowledge Base Statistics\n")
        click.echo(f"Location: {kb_path}")
        click.echo(f"Total facts: {stats['total_facts']}")
        click.echo(f"Facts needing refresh: {stats['facts_needing_refresh']}")
        click.echo()
        click.echo("Facts by type:")
        for fact_type, count in stats["facts_by_type"].items():
            click.echo(f"  {fact_type}: {count}")
        click.echo()
        click.echo("Facts by source:")
        for source, count in stats["facts_by_source"].items():
            click.echo(f"  {source}: {count}")
        click.echo()
        click.echo("Generations:")
        click.echo(f"  Total: {stats['total_generations']}")
        click.echo(f"  Successful: {stats.get('successful_generations', 0)}")
        click.echo(f"  Failed: {stats.get('failed_generations', 0)}")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise click.ClickException(f"Error: {e}")


@profile.command()
@click.option("--output", "-o", default=None, help="Path to output JSON file")
def dump(output: str | None) -> None:
    """Export knowledge base to JSON."""
    import json
    from pathlib import Path as PathlibPath
    from .knowledge import KnowledgeBase

    try:
        kb_dir = PathlibPath.home() / ".fast-app"
        kb_path = kb_dir / "knowledge.db"

        if not kb_path.exists():
            click.echo("\n⚠️  Knowledge base not found.")
            click.echo(f"   Expected at: {kb_path}")
            return

        kb = KnowledgeBase(str(kb_path))
        data = kb.export_to_json()

        if output:
            output_path = PathlibPath(output)
        else:
            output_path = kb_dir / "knowledge_export.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, indent=2))
        click.echo(f"Exported {len(data['facts'])} facts to {output_path}")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise click.ClickException(f"Error: {e}")


@profile.command()
@click.argument("json_file", type=click.Path(exists=True))
def load(json_file: str) -> None:
    """Import knowledge base from JSON file."""
    import json
    from pathlib import Path as PathlibPath
    from .knowledge import KnowledgeBase

    try:
        kb_dir = PathlibPath.home() / ".fast-app"
        kb_path = kb_dir / "knowledge.db"

        kb_dir.mkdir(parents=True, exist_ok=True)

        kb = KnowledgeBase(str(kb_path))
        json_path = PathlibPath(json_file)
        data = json.loads(json_path.read_text())

        kb.import_from_json(data)
        click.echo(f"Imported {len(data['facts'])} facts")

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Error: {e}")
        raise click.ClickException(f"Error: {e}")


if __name__ == "__main__":
    main()

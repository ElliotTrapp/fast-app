"""CLI for fast-app."""

import copy
import json
import re
import uuid
from pathlib import Path
from typing import Any

import click

from .config import load_config
from .log import logger
from .models import ProfileData
from .services.cache import CacheManager, generate_job_id
from .services.job_extractor import JobExtractor
from .services.ollama import OllamaService
from .services.reactive_resume import ReactiveResumeClient


def sanitize_name(name: str) -> str:
    """Sanitize name by removing commas, extra spaces, and special characters."""
    # Remove commas
    name = name.replace(",", "")
    # Remove special characters except spaces and hyphens
    name = re.sub(r"[^\w\s-]", "", name)
    # Replace multiple spaces with single space
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def find_profile_file(cli_path: str | None = None) -> Path:
    """Find profile file in order of precedence.

    Order:
    1. CLI --profile flag
    2. ./profile.json
    3. ../easy-apply/profile.json (sibling directory)
    4. Error if not found
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Profile file not found: {path}")

    cwd_path = Path.cwd() / "profile.json"
    if cwd_path.exists():
        return cwd_path

    sibling_path = Path.cwd().parent / "easy-apply" / "profile.json"
    if sibling_path.exists():
        return sibling_path

    raise FileNotFoundError(
        "No profile file found. Checked:\n"
        f"  1. --profile flag\n"
        f"  2. {cwd_path}\n"
        f"  3. {sibling_path}\n"
        "Create a profile.json file or specify --profile"
    )


def find_base_resume_file(cli_path: str | None = None) -> Path | None:
    """Find base resume template file.

    Order:
    1. CLI --base flag
    2. ./base-resume.json
    3. None (return None)
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        return None

    cwd_path = Path.cwd() / "base-resume.json"
    if cwd_path.exists():
        return cwd_path

    return None


def find_base_cover_letter_file(cli_path: str | None = None) -> Path | None:
    """Find base cover letter template file.

    Order:
    1. CLI --base-cover-letter flag
    2. ./base-cover-letter.json
    3. None (return None)
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        return None

    cwd_path = Path.cwd() / "base-cover-letter.json"
    if cwd_path.exists():
        return cwd_path

    return None


def load_profile(cli_path: str | None = None) -> dict:
    """Load profile from file."""
    profile_path = find_profile_file(cli_path)
    data = json.loads(profile_path.read_text())
    return ProfileData.model_validate(data).model_dump()


def load_base_resume(cli_path: str | None = None) -> dict | None:
    """Load base resume template from file."""
    base_path = find_base_resume_file(cli_path)
    if base_path:
        return json.loads(base_path.read_text())
    return None


def load_base_cover_letter(cli_path: str | None = None) -> dict | None:
    """Load base cover letter template from file."""
    base_path = find_base_cover_letter_file(cli_path)
    if base_path:
        return json.loads(base_path.read_text())
    return None


def merge_resume_with_base(generated: dict, base: dict | None) -> dict:
    """Merge generated resume data with base template.

    The base template provides styling/theme settings, and generated
    data provides the content (basics, summary, sections).
    Preserves columns and other styling fields from base.
    """
    if base:
        result = base.copy()

        # Merge basics - preserve base fields not in generated
        generated_basics = generated.get("basics", {})
        result["basics"] = {**result.get("basics", {}), **generated_basics}

        # Merge summary - preserve title, columns, hidden from base
        generated_summary = generated.get("summary", {})
        base_summary = result.get("summary", {})
        result["summary"] = {
            "title": base_summary.get("title", ""),
            "columns": base_summary.get("columns", 1),
            "hidden": base_summary.get("hidden", False),
            "content": generated_summary.get("content", "<p></p>"),
        }

        # Merge sections - preserve title, columns, hidden from base for each section
        generated_sections = generated.get("sections", {})
        base_sections = result.get("sections", {})
        merged_sections = {}

        for section_name in generated_sections:
            base_section = base_sections.get(section_name, {})
            generated_section = generated_sections.get(section_name, {})

            merged_sections[section_name] = {
                "title": base_section.get("title", ""),
                "columns": base_section.get("columns", 1),
                "hidden": base_section.get("hidden", False),
                "items": generated_section.get("items", []),
            }

        result["sections"] = merged_sections
    else:
        result = generated.copy()

    return result


def check_existing_resume(
    rr_client: ReactiveResumeClient,
    cache: CacheManager,
    job_dir: Path,
    resume_title: str,
    overwrite: bool,
) -> str | None:
    """Check for existing resume/cover letter and handle --overwrite flag.

    Args:
        rr_client: Reactive Resume client
        cache: Cache manager
        job_dir: Job directory
        resume_title: Title of the resume/cover letter
        overwrite: Whether to overwrite existing

    Returns:
        Resume ID if one exists (or None if deleted)

    Raises:
        click.ClickException: If resume exists and overwrite is False
    """
    cached_reactive = cache.get_cached_reactive_resume(job_dir)
    existing_id: str | None = None

    if cached_reactive:
        existing_id = cached_reactive.get("resume_id")
        if existing_id:
            resume_check = rr_client.get_resume(existing_id)
            if not resume_check:
                existing_id = None

    if not existing_id:
        existing_id = rr_client.find_resume_by_title(resume_title)

    if existing_id and not overwrite:
        logger.error(f"Resume '{resume_title}' already exists")
        click.echo(
            click.style(
                f"\n❌ Error: Resume '{resume_title}' already exists in Reactive Resume.",
                fg="red",
            )
        )
        click.echo(click.style("   Use --overwrite-resume to replace it.", fg="yellow"))
        raise click.ClickException(
            f"Resume '{resume_title}' already exists. Use --overwrite-resume to overwrite."
        )

    if existing_id and overwrite:
        logger.warning(f"Deleting existing resume: {existing_id}")
        rr_client.delete_resume(existing_id)
        return None

    return existing_id


def merge_cover_letter_with_base(
    generated: dict, profile: dict, base: dict | None, job_title: str, company: str
) -> dict:
    """Merge generated cover letter content with base template.

    The base template provides styling/theme settings, generated data
    provides the recipient and content.
    """
    if base:
        result = copy.deepcopy(base)
    else:
        result = {}

    # Convert profile basics to Reactive Resume format
    profile_basics = profile.get("basics", {})

    # Convert location from object to string
    location = ""
    if isinstance(profile_basics.get("location"), dict):
        loc = profile_basics["location"]
        parts = []
        if loc.get("city"):
            parts.append(loc["city"])
        if loc.get("region"):
            parts.append(loc["region"])
        if loc.get("countryCode"):
            parts.append(loc["countryCode"])
        location = ", ".join(parts)
    elif isinstance(profile_basics.get("location"), str):
        location = profile_basics["location"]

    # Convert url to website object
    website = {"url": "", "label": ""}
    if profile_basics.get("url"):
        url = profile_basics["url"]
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        website = {"url": url, "label": url}

    result["basics"] = {
        "name": profile_basics.get("name", ""),
        "headline": profile_basics.get("label", ""),
        "email": profile_basics.get("email", ""),
        "phone": profile_basics.get("phone", ""),
        "location": location,
        "website": website,
        "customFields": [],
    }

    result["summary"] = {
        "title": "",
        "columns": 1,
        "hidden": True,
        "content": "<p></p>",
    }

    for section_name in result.get("sections", {}):
        result["sections"][section_name]["hidden"] = True
        result["sections"][section_name]["items"] = []

    cover_letter_id = str(uuid.uuid4())

    result["customSections"] = [
        {
            "title": "Cover Letter",
            "columns": 1,
            "hidden": False,
            "id": cover_letter_id,
            "type": "cover-letter",
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "hidden": False,
                    "recipient": generated.get("recipient", ""),
                    "content": generated.get("content", ""),
                }
            ],
        }
    ]

    # Add the cover letter section ID to the layout's main array
    if "metadata" in result and "layout" in result["metadata"]:
        layout = result["metadata"]["layout"]
        if "pages" in layout and len(layout["pages"]) > 0:
            # Add cover letter section to main array
            if cover_letter_id not in layout["pages"][0]["main"]:
                layout["pages"][0]["main"].append(cover_letter_id)
    else:
        # Create metadata if it doesn't exist
        result["metadata"] = {
            "template": "onyx",
            "layout": {
                "sidebarWidth": 20,
                "pages": [{"fullWidth": True, "main": [cover_letter_id], "sidebar": []}],
            },
            "css": {"enabled": False, "value": ""},
            "page": {
                "gapX": 4,
                "gapY": 6,
                "marginX": 14,
                "marginY": 12,
                "format": "free-form",
                "locale": "en-US",
                "hideIcons": False,
            },
            "design": {
                "level": {"icon": "star", "type": "circle"},
                "colors": {
                    "primary": "rgba(0, 153, 102, 1)",
                    "text": "rgba(0, 0, 0, 1)",
                    "background": "rgba(255, 255, 255, 1)",
                },
            },
            "typography": {
                "body": {
                    "fontFamily": "IBM Plex Serif",
                    "fontWeights": ["400", "500"],
                    "fontSize": 10,
                    "lineHeight": 1.5,
                },
                "heading": {
                    "fontFamily": "IBM Plex Serif",
                    "fontWeights": ["600"],
                    "fontSize": 14,
                    "lineHeight": 1.5,
                },
            },
            "notes": "",
        }

    return result


def ask_questions_interactive(questions: list[str]) -> list[str]:
    """Ask questions interactively and collect answers.

    Supports multiline answers - user can press Enter twice to submit,
    or Escape + Enter to finish a multiline answer.
    """
    answers = []
    click.echo("\n📝 Please answer these questions to help tailor your resume:\n")
    click.echo(click.style("   Tip: Press Enter twice to finish a multiline answer", fg="cyan"))
    click.echo()

    for i, question in enumerate(questions, 1):
        click.echo(f"{i}. {question}")
        click.echo("   " + "─" * 60)

        lines = []
        empty_line_count = 0

        while True:
            try:
                line = click.prompt("   ", default="", show_default=False, prompt_suffix="")

                if line == "":
                    empty_line_count += 1
                    if empty_line_count >= 1 and lines:
                        break
                else:
                    empty_line_count = 0
                    lines.append(line)
            except (KeyboardInterrupt, EOFError):
                if lines:
                    break
                click.echo("\n   Skipping this question...")
                break

        answer = "\n".join(lines).strip()
        answers.append(answer)
        click.echo()

    return answers


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
    help="Save generated JSON to file (for debugging)",
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
    help="Show detailed output",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Show LLM prompts and responses",
)
@click.option(
    "--skip-questions",
    is_flag=True,
    help="Skip questionnaire and generate resume directly",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Regenerate files even if cached",
)
@click.option(
    "--overwrite-resume",
    is_flag=True,
    help="Overwrite existing resume with same title if it exists",
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
def generate(
    url: str,
    profile_path: str | None,
    base_path: str | None,
    config_path: str | None,
    output: str | None,
    api_key: str | None,
    verbose: bool,
    debug: bool,
    skip_questions: bool,
    force: bool,
    overwrite_resume: bool,
    skip_cover_letter: bool,
    base_cover_letter: str | None,
):
    """Generate and import resume for job URL.

    URL: The job posting URL to generate a resume for.
    """
    try:
        # Set global debug mode
        logger.debug = debug

        config = load_config(config_path)

        if api_key:
            config.resume.api_key = api_key

        output_dir = Path.cwd() / config.output.directory
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.header("Configuration")
        logger.detail("output_dir", str(output_dir))
        logger.detail("force", force)
        logger.detail("skip_questions", skip_questions)
        logger.detail("debug", debug)

        cache = CacheManager(output_dir)
        profile = load_profile(profile_path)
        base_resume = load_base_resume(base_path)

        logger.header("Files")
        logger.detail("profile_path", str(find_profile_file(profile_path)))
        if base_path:
            logger.detail("base_resume_path", str(find_base_resume_file(base_path)))

        ollama = OllamaService(config.ollama)
        job_extractor = JobExtractor(ollama.client, config.ollama.model)
        rr_client = ReactiveResumeClient(config.resume.endpoint, config.resume.api_key)

        if not ollama.check_connection():
            raise click.ClickException(
                f"Cannot connect to Ollama at {config.ollama.endpoint}. "
                "Make sure Ollama is running."
            )

        if verbose:
            logger.success(f"Connected to Ollama at {config.ollama.endpoint}")

        if not ollama.ensure_model_available():
            raise click.ClickException(
                f"Model '{config.ollama.model}' not available. "
                "Run 'ollama pull {config.ollama.model}' first."
            )

        job_id = generate_job_id(url)
        questions = []
        answers = []
        resume_data = None
        job_description = ""
        used_cache = False
        job_data = None
        job_title = ""
        company = ""
        job_dir = None

        if not force:
            logger.cache_search("hash", job_id)
            cached_job_dir = cache.find_job_by_hash(job_id)
            if cached_job_dir:
                logger.cache_found(str(cached_job_dir))
                click.echo(click.style(f"♻️  Found cached job: {cached_job_dir}", fg="green"))

                job_data = cache.get_cached_job(cached_job_dir)
                if not job_data:
                    logger.error("Failed to load cached job data")
                    raise click.ClickException("Failed to load cached job data")

                raw_title = job_data.get("title", "Unknown")
                raw_company = job_data.get("company", "Unknown")
                job_title = sanitize_name(raw_title)
                company = sanitize_name(raw_company)
                job_description = job_data.get("description", "")
                job_dir = cached_job_dir

                cached_questions = cache.get_cached_questions(job_dir) or []
                cached_answers = cache.get_cached_answers(job_dir) or []
                cached_resume = cache.get_cached_resume(job_dir)

                if cached_resume and (
                    len(cached_questions) == len(cached_answers) if cached_questions else True
                ):
                    used_cache = True
                    questions = cached_questions
                    answers = cached_answers
                    click.echo(f"   Found: {job_title} at {company}")
                    logger.success("Using cached resume data")

                    final_resume = merge_resume_with_base(cached_resume, base_resume)
                    resume_title = f"{job_title} at {company} Resume"

                    # Check for cached reactive resume ID
                    cached_reactive = cache.get_cached_reactive_resume(job_dir)
                    existing_id = None

                    if cached_reactive:
                        existing_id = cached_reactive.get("resume_id")
                        # Verify it still exists
                        if existing_id:
                            resume_check = rr_client.get_resume(existing_id)
                            if not resume_check:
                                existing_id = None

                    # If not cached, search by title
                    if not existing_id:
                        existing_id = rr_client.find_resume_by_title(resume_title)

                    if existing_id and not overwrite_resume:
                        logger.error(f"Resume '{resume_title}' already exists")
                        click.echo(
                            click.style(
                                f"\n❌ Error: Resume '{resume_title}' already exists in Reactive Resume.",
                                fg="red",
                            )
                        )
                        click.echo(
                            click.style("   Use --overwrite-resume to replace it.", fg="yellow")
                        )
                        raise click.ClickException(
                            f"Resume '{resume_title}' already exists. Use --overwrite-resume to overwrite."
                        )

                    if existing_id and overwrite_resume:
                        logger.warning(f"Deleting existing resume: {existing_id}")
                        rr_client.delete_resume(existing_id)
                        existing_id = None

                    # Add notes with URL and description
                    final_resume["metadata"]["notes"] = f"{url}\n\n{job_description}"

                    click.echo("\n🚀 Creating resume in Reactive Resume...")

                    # Create resume with title
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

        if not used_cache:
            click.echo(f"🔍 Extracting job data from {url}...")
            job_data = job_extractor.extract_from_url(url)
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
                    click.echo("\n🤖 Generating questions to tailor your resume...")
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

            resume_path = job_dir / "resume.json"

            if not force and resume_path.exists():
                resume_data = cache.get_cached_resume(job_dir)
                logger.cache_hit("resume", str(resume_path))
                if verbose and not debug:
                    logger.success("Using cached resume data")
            else:
                click.echo("\n📝 Generating tailored resume...")
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

            resume_title = f"{job_title} at {company} Resume"

            # Check for cached reactive resume ID
            cached_reactive = cache.get_cached_reactive_resume(job_dir)
            existing_id = None

            if cached_reactive:
                existing_id = cached_reactive.get("resume_id")
                # Verify it still exists
                if existing_id:
                    resume_check = rr_client.get_resume(existing_id)
                    if not resume_check:
                        existing_id = None

            # If not cached, search by title
            if not existing_id:
                existing_id = rr_client.find_resume_by_title(resume_title)

            if existing_id and not overwrite_resume:
                logger.error(f"Resume '{resume_title}' already exists")
                click.echo(
                    click.style(
                        f"\n❌ Error: Resume '{resume_title}' already exists in Reactive Resume.",
                        fg="red",
                    )
                )
                click.echo(click.style("   Use --overwrite-resume to replace it.", fg="yellow"))
                raise click.ClickException(
                    f"Resume '{resume_title}' already exists. Use --overwrite-resume to overwrite."
                )

            if existing_id and overwrite_resume:
                logger.warning(f"Deleting existing resume: {existing_id}")
                rr_client.delete_resume(existing_id)
                existing_id = None

            logger.header("Resume Creation")
            logger.detail("title", resume_title)
            logger.detail("company", company)

            # Add notes with URL and description
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

        if not skip_cover_letter:
            base_cover_letter = load_base_cover_letter(base_cover_letter)
            cover_letter_path = job_dir / "cover_letter.json"
            cover_letter_data = None

            if not force and cover_letter_path.exists():
                cover_letter_data = cache.get_cached_cover_letter(job_dir)
                logger.cache_hit("cover_letter", str(cover_letter_path))
                if verbose and not debug:
                    logger.success("Using cached cover letter data")

            if not cover_letter_data:
                click.echo("\n✍️  Generating cover letter...")
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

            final_cover_letter = merge_cover_letter_with_base(
                cover_letter_data, profile, base_cover_letter, job_title, company
            )

            cover_letter_title = f"{job_title} at {company} Cover Letter"

            # Check for cached reactive cover letter ID
            cached_reactive_cl = cache.get_cached_reactive_cover_letter(job_dir)
            existing_cl_id = None

            if cached_reactive_cl:
                existing_cl_id = cached_reactive_cl.get("cover_letter_id")
                if existing_cl_id:
                    cl_check = rr_client.get_resume(existing_cl_id)
                    if not cl_check:
                        existing_cl_id = None

            if not existing_cl_id:
                existing_cl_id = rr_client.find_resume_by_title(cover_letter_title)

            if existing_cl_id and overwrite_resume:
                logger.warning(f"Deleting existing cover letter: {existing_cl_id}")
                rr_client.delete_resume(existing_cl_id)
                existing_cl_id = None

            # Add notes with URL and description
            final_cover_letter["metadata"]["notes"] = f"{url}\n\n{job_description}"

            click.echo("\n🚀 Creating cover letter in Reactive Resume...")

            # Create cover letter with unique slug to avoid collision with resume
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

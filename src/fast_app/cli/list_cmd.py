"""List CLI command."""

from pathlib import Path
from typing import Any

import click

from ..config import load_config
from ..log import logger
from ..services.cache import CacheManager


def register_commands(main: click.Group) -> None:
    """Register list commands on the main group."""
    main.add_command(list_jobs)


@click.command("list")
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

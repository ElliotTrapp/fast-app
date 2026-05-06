"""CLI-specific pipeline callbacks using Click for I/O."""

import click

from ..log import logger


class CLICallbacks:
    """Pipeline callbacks for CLI (Click-based) I/O."""

    def __init__(self, verbose: bool = False, debug: bool = False):
        self.verbose = verbose
        self.debug = debug

    async def on_state_change(self, old_state: str, new_state: str) -> None:
        pass

    async def on_progress(self, step: str, progress: float) -> None:
        pass

    def on_job_extracted(self, job_title: str, company: str) -> None:
        click.echo(f"   Found: {job_title} at {company}")

    def on_cache_hit(self, item: str, path: str) -> None:
        logger.cache_hit(item, path)
        if self.verbose and not self.debug:
            logger.success(f"Using cached {item}")

    def on_cache_save(self, item: str, path: str) -> None:
        logger.cache_save(item, path)
        if self.verbose and not self.debug:
            click.echo(f"   💾 Saved: {item}")

    async def collect_answers(self, questions: list[str]) -> list[str]:
        from ..utils.interactive import ask_questions_interactive

        return ask_questions_interactive(questions)

    def review_facts(self, facts: list) -> list | None:
        click.echo("\n📝 Extracted facts:")
        for i, fact in enumerate(facts, 1):
            click.echo(f"  {i}. [{fact.category}] {fact.content}")
        if not click.confirm("Store these facts?"):
            click.echo("   Skipping fact storage.")
            return None
        return facts

    def raise_already_exists(self, item_type: str, identifier: str) -> None:
        raise click.ClickException(
            f"{identifier} already exists. Use --overwrite-resume to overwrite."
        )

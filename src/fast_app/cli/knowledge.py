"""Knowledge CLI command group (search, list, delete)."""

import click

from ..config import load_config
from ..log import logger


def register_commands(main: click.Group) -> None:
    """Register knowledge commands on the main group."""
    main.add_command(knowledge)


@click.group()
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
    from .auth import _get_user_id

    try:
        from ..services.knowledge import KnowledgeService

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
    from .auth import _get_user_id

    try:
        from ..services.knowledge import KnowledgeService

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
    from .auth import _get_user_id

    try:
        from ..services.knowledge import KnowledgeService

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

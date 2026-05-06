"""Profile CLI command group (list, import, export, set-default, delete)."""

import json
from pathlib import Path

import click

from ..config import load_config
from ..log import logger


def register_commands(main: click.Group) -> None:
    """Register profile commands on the main group."""
    main.add_command(profile)


@click.group()
def profile():
    """Profile management commands (list, import, export, set-default, delete)."""
    pass


@profile.command("list")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
def profile_list(config_path: str | None) -> None:
    """List all profiles for the current user."""
    from .auth import _get_user_id

    try:
        from ..db import get_session, init_db
        from ..services.profile_service import ProfileService

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
    from .auth import _get_user_id

    try:
        from ..db import get_session, init_db
        from ..services.profile_service import ProfileService

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
                from ..services.fact_extractor import FactExtractor
                from ..services.knowledge import KnowledgeService
                from ..services.llm_service import LLMService

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
    from .auth import _get_user_id

    try:
        from ..db import get_session, init_db
        from ..services.profile_service import ProfileService

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
    from .auth import _get_user_id

    try:
        from ..db import get_session, init_db
        from ..models.db_models import ProfileCreate
        from ..services.profile_service import ProfileService

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
    from .auth import _get_user_id

    try:
        from ..db import get_session, init_db
        from ..services.profile_service import ProfileService

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

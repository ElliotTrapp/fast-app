"""Status and serve CLI commands."""

from pathlib import Path

import click

from ..config import load_config
from ..log import logger
from ..services.ollama import OllamaService
from ..services.reactive_resume import ReactiveResumeClient
from ..utils import find_profile_file


def register_commands(main: click.Group) -> None:
    """Register status and serve commands on the main group."""
    main.add_command(status_command)
    main.add_command(serve)


@click.command("status")
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


@click.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
@click.option("--config", "-c", default=None, help="Config file path")
def serve(host: str, port: int, config: str | None) -> None:
    """Start Fast-App web server.

    Launches a web interface for generating resumes.
    Checks connections and configuration before starting.
    """
    import uvicorn

    try:
        config_obj = load_config(config)

        click.echo("🔍 Validating connections...\n")

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

        from ..webapp.app import app as webapp

        uvicorn.run(webapp, host=host, port=port, log_level="info", access_log=False)

    except FileNotFoundError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise click.ClickException(f"Server error: {e}")

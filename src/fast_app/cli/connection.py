"""Test-connection CLI command."""

import click

from ..config import load_config
from ..log import logger
from ..services.ollama import OllamaService
from ..services.reactive_resume import ReactiveResumeClient


def register_commands(main: click.Group) -> None:
    """Register connection commands on the main group."""
    main.add_command(test_connection)


@click.command("test-connection")
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

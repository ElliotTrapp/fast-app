"""Configuration management with XDG-compliant loading."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OllamaConfig:
    endpoint: str = "http://localhost:11434"
    model: str = "llama3.2"
    cloud: bool = False
    debug: bool = False
    api_key: str = ""


@dataclass
class ReactiveResumeConfig:
    endpoint: str = "http://localhost:3000"
    api_key: str = ""


@dataclass
class OutputConfig:
    directory: str = "generated"


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    resume: ReactiveResumeConfig = field(default_factory=ReactiveResumeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        ollama_data = data.get("ollama", {})
        resume_data = data.get("resume", {})
        output_data = data.get("output", {})

        return cls(
            ollama=OllamaConfig(
                endpoint=ollama_data.get("endpoint", "http://localhost:11434"),
                model=ollama_data.get("model", "llama3.2"),
                cloud=ollama_data.get("cloud", False),
                debug=ollama_data.get("debug", False),
                api_key=ollama_data.get("api_key", ""),
            ),
            resume=ReactiveResumeConfig(
                endpoint=resume_data.get("endpoint", "http://localhost:3000"),
                api_key=resume_data.get("api_key", ""),
            ),
            output=OutputConfig(
                directory=output_data.get("directory", "generated"),
            ),
        )

    @classmethod
    def from_file(cls, path: str) -> "Config":
        file_path = Path(path).expanduser()

        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = json.load(f)

        config = cls.from_dict(data)

        # Override with environment variables if set
        if os.environ.get("OLLAMA_ENDPOINT"):
            config.ollama.endpoint = os.environ["OLLAMA_ENDPOINT"]
        if os.environ.get("OLLAMA_MODEL"):
            config.ollama.model = os.environ["OLLAMA_MODEL"]
        if os.environ.get("RESUME_ENDPOINT"):
            config.resume.endpoint = os.environ["RESUME_ENDPOINT"]
        if os.environ.get("RESUME_API_KEY"):
            config.resume.api_key = os.environ["RESUME_API_KEY"]

        return config


def find_config_file(cli_path: str | None = None) -> Path:
    """Find config file in order of precedence.

    Order:
    1. CLI --config flag
    2. FAST_APP_CONFIG env var
    3. ./config.json
    4. ~/.config/fast-app/config.json

    Raises FileNotFoundError if not found.
    """
    if cli_path:
        path = Path(cli_path).expanduser()
        if path.exists():
            return path
        raise FileNotFoundError(f"Config file not found: {path}")

    env_path = os.environ.get("FAST_APP_CONFIG")
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path

    cwd_path = Path.cwd() / "config.json"
    if cwd_path.exists():
        return cwd_path

    xdg_config = os.environ.get("XDG_CONFIG_HOME", "~/.config")
    xdg_path = Path(xdg_config).expanduser() / "fast-app" / "config.json"
    if xdg_path.exists():
        return xdg_path

    raise FileNotFoundError(
        "No config file found. Checked:\n"
        f"  1. --config flag\n"
        f"  2. FAST_APP_CONFIG env var\n"
        f"  3. {cwd_path}\n"
        f"  4. {xdg_path}\n"
        "Create a config.json file or specify --config"
    )


def load_config(cli_path: str | None = None) -> Config:
    """Load configuration from file."""
    config_path = find_config_file(cli_path)
    return Config.from_file(str(config_path))

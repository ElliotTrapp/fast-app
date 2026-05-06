"""Configuration management with environment variable loading.

Configuration is loaded from environment variables with sensible defaults.
A config.json file can optionally be used via --config flag or FAST_APP_CONFIG
env var, but is not required — all settings have defaults that can be
overridden via environment variables.

## Priority Order (highest to lowest)

1. CLI flags (e.g., --provider, --model)
2. Environment variables (FAST_APP_*)
3. config.json file (optional, via --config or FAST_APP_CONFIG)
4. Built-in defaults

See: docs/guide/llm-providers.md, docs/adr/003-env-only-config.md
"""

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
class AuthConfig:
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440


@dataclass
class DatabaseConfig:
    path: str = ""


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = ""
    temperature: float = 0.3
    base_url: str = ""
    api_key: str = ""


@dataclass
class ChromaConfig:
    path: str = ""
    embedding_model: str = "nomic-embed-text"
    client_type: str = "persistent"
    host: str = "localhost"
    port: int = 8000


@dataclass
class JSearchConfig:
    """Configuration for the JSearch job search API (RapidAPI)."""

    api_key: str = ""  # RAPIDAPI_KEY
    base_url: str = "https://jsearch.p.rapidapi.com"


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    reactive_resume: ReactiveResumeConfig = field(default_factory=ReactiveResumeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    jsearch: JSearchConfig = field(default_factory=JSearchConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        """Create Config from a dictionary (e.g., parsed from config.json).

        Supports both legacy keys ("resume", "database.jwt_*") and new keys
        ("reactive_resume", "auth.jwt_*") for backward compatibility.
        """
        ollama_data = data.get("ollama", {})
        resume_data = data.get("resume", data.get("reactive_resume", {}))
        output_data = data.get("output", {})
        database_data = data.get("database", {})
        auth_data = data.get("auth", {})
        llm_data = data.get("llm", {})
        chroma_data = data.get("chroma", {})
        jsearch_data = data.get("jsearch", {})

        llm_model = llm_data.get("model", "")

        return cls(
            ollama=OllamaConfig(
                endpoint=ollama_data.get("endpoint", "http://localhost:11434"),
                model=ollama_data.get("model", "llama3.2"),
                cloud=ollama_data.get("cloud", False),
                debug=ollama_data.get("debug", False),
                api_key=ollama_data.get("api_key", ""),
            ),
            reactive_resume=ReactiveResumeConfig(
                endpoint=resume_data.get("endpoint", "http://localhost:3000"),
                api_key=resume_data.get("api_key", ""),
            ),
            output=OutputConfig(
                directory=output_data.get("directory", "generated"),
            ),
            database=DatabaseConfig(
                path=database_data.get("path", ""),
            ),
            auth=AuthConfig(
                jwt_secret=auth_data.get("jwt_secret", database_data.get("jwt_secret", "")),
                jwt_algorithm=auth_data.get("jwt_algorithm", "HS256"),
                jwt_expire_minutes=auth_data.get("jwt_expire_minutes", 1440),
            ),
            llm=LLMConfig(
                provider=llm_data.get("provider", "ollama"),
                model=llm_model,
                temperature=llm_data.get("temperature", 0.3),
                base_url=llm_data.get("base_url", ""),
                api_key=llm_data.get("api_key", ""),
            ),
            chroma=ChromaConfig(
                path=chroma_data.get("path", ""),
                embedding_model=chroma_data.get("embedding_model", "nomic-embed-text"),
                client_type=chroma_data.get("client_type", "persistent"),
                host=chroma_data.get("host", "localhost"),
                port=chroma_data.get("port", 8000),
            ),
            jsearch=JSearchConfig(
                api_key=jsearch_data.get("api_key", ""),
                base_url=jsearch_data.get("base_url", "https://jsearch.p.rapidapi.com"),
            ),
        )

    @classmethod
    def from_env(cls) -> "Config":
        """Create Config from environment variables and built-in defaults.

        This is the primary configuration method. All settings have defaults
        that can be overridden via FAST_APP_* environment variables.
        """
        config = cls()

        # Ollama settings
        if os.environ.get("OLLAMA_ENDPOINT"):
            config.ollama.endpoint = os.environ["OLLAMA_ENDPOINT"]
        if os.environ.get("OLLAMA_MODEL"):
            config.ollama.model = os.environ["OLLAMA_MODEL"]

        # Reactive Resume settings
        if os.environ.get("RESUME_ENDPOINT"):
            config.reactive_resume.endpoint = os.environ["RESUME_ENDPOINT"]
        if os.environ.get("RESUME_API_KEY"):
            config.reactive_resume.api_key = os.environ["RESUME_API_KEY"]

        # Database settings
        if os.environ.get("FAST_APP_DB_PATH"):
            config.database.path = os.environ["FAST_APP_DB_PATH"]

        # Auth settings
        if os.environ.get("FAST_APP_JWT_SECRET"):
            config.auth.jwt_secret = os.environ["FAST_APP_JWT_SECRET"]
        if os.environ.get("FAST_APP_JWT_EXPIRE_MINUTES"):
            config.auth.jwt_expire_minutes = int(os.environ["FAST_APP_JWT_EXPIRE_MINUTES"])

        # LLM settings
        if os.environ.get("FAST_APP_LLM_PROVIDER"):
            config.llm.provider = os.environ["FAST_APP_LLM_PROVIDER"]
        if os.environ.get("FAST_APP_LLM_MODEL"):
            config.llm.model = os.environ["FAST_APP_LLM_MODEL"]
        if os.environ.get("FAST_APP_LLM_BASE_URL"):
            config.llm.base_url = os.environ["FAST_APP_LLM_BASE_URL"]
        if os.environ.get("FAST_APP_LLM_API_KEY"):
            config.llm.api_key = os.environ["FAST_APP_LLM_API_KEY"]

        # ChromaDB settings
        if os.environ.get("FAST_APP_CHROMA_PATH"):
            config.chroma.path = os.environ["FAST_APP_CHROMA_PATH"]
        if os.environ.get("FAST_APP_CHROMA_EMBEDDING_MODEL"):
            config.chroma.embedding_model = os.environ["FAST_APP_CHROMA_EMBEDDING_MODEL"]
        if os.environ.get("FAST_APP_CHROMA_CLIENT_TYPE"):
            config.chroma.client_type = os.environ["FAST_APP_CHROMA_CLIENT_TYPE"]

        # JSearch settings
        if os.environ.get("FAST_APP_JSEARCH_API_KEY"):
            config.jsearch.api_key = os.environ["FAST_APP_JSEARCH_API_KEY"]

        return config

    @classmethod
    def from_file(cls, path: str) -> "Config":
        """Load Config from a JSON file, then apply env var overrides.

        This is for backward compatibility with config.json files.
        Environment variables take precedence over file values.
        """
        file_path = Path(path).expanduser()

        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = json.load(f)

        # Start with file values, then overlay env vars
        return cls.from_dict(data)._apply_env_overrides()

    def _apply_env_overrides(self) -> "Config":
        """Apply environment variable overrides to an existing config.

        Environment variables take precedence over all other sources.
        """
        if os.environ.get("OLLAMA_ENDPOINT"):
            self.ollama.endpoint = os.environ["OLLAMA_ENDPOINT"]
        if os.environ.get("OLLAMA_MODEL"):
            self.ollama.model = os.environ["OLLAMA_MODEL"]
        if os.environ.get("RESUME_ENDPOINT"):
            self.reactive_resume.endpoint = os.environ["RESUME_ENDPOINT"]
        if os.environ.get("RESUME_API_KEY"):
            self.reactive_resume.api_key = os.environ["RESUME_API_KEY"]
        if os.environ.get("FAST_APP_DB_PATH"):
            self.database.path = os.environ["FAST_APP_DB_PATH"]
        if os.environ.get("FAST_APP_JWT_SECRET"):
            self.auth.jwt_secret = os.environ["FAST_APP_JWT_SECRET"]
        if os.environ.get("FAST_APP_JWT_EXPIRE_MINUTES"):
            self.auth.jwt_expire_minutes = int(os.environ["FAST_APP_JWT_EXPIRE_MINUTES"])
        if os.environ.get("FAST_APP_LLM_PROVIDER"):
            self.llm.provider = os.environ["FAST_APP_LLM_PROVIDER"]
        if os.environ.get("FAST_APP_LLM_MODEL"):
            self.llm.model = os.environ["FAST_APP_LLM_MODEL"]
        if os.environ.get("FAST_APP_LLM_BASE_URL"):
            self.llm.base_url = os.environ["FAST_APP_LLM_BASE_URL"]
        if os.environ.get("FAST_APP_LLM_API_KEY"):
            self.llm.api_key = os.environ["FAST_APP_LLM_API_KEY"]
        if os.environ.get("FAST_APP_CHROMA_PATH"):
            self.chroma.path = os.environ["FAST_APP_CHROMA_PATH"]
        if os.environ.get("FAST_APP_CHROMA_EMBEDDING_MODEL"):
            self.chroma.embedding_model = os.environ["FAST_APP_CHROMA_EMBEDDING_MODEL"]
        if os.environ.get("FAST_APP_CHROMA_CLIENT_TYPE"):
            self.chroma.client_type = os.environ["FAST_APP_CHROMA_CLIENT_TYPE"]
        if os.environ.get("FAST_APP_JSEARCH_API_KEY"):
            self.jsearch.api_key = os.environ["FAST_APP_JSEARCH_API_KEY"]
        return self


def find_config_file(cli_path: str | None = None) -> Path | None:
    """Find an optional config file.

    Search order:
    1. CLI --config flag (must exist if specified)
    2. FAST_APP_CONFIG env var
    3. ./config.json
    4. ~/.config/fast-app/config.json

    Returns None if no config file is found (which is fine —
    config works with env vars and defaults alone).
    Raises FileNotFoundError only if an explicit --config path doesn't exist.
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

    return None


def load_config(cli_path: str | None = None) -> Config:
    """Load configuration from environment variables and optional config file.

    Loads .env file first (if python-dotenv is installed), then applies
    config file values (if found), then applies env var overrides on top.

    If a config file is found (via --config flag, FAST_APP_CONFIG env var,
    or default locations), it is loaded first and then env vars override.
    If no config file exists, configuration comes entirely from env vars
    with sensible built-in defaults.
    """
    from .dotenv import load_dotenv

    load_dotenv()

    config_path = find_config_file(cli_path)
    if config_path is not None:
        return Config.from_file(str(config_path))
    return Config.from_env()

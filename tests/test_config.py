"""Unit tests for configuration loading."""

import json
import tempfile
from pathlib import Path

import pytest

from fast_app.config import (
    Config,
    OllamaConfig,
    OutputConfig,
    ReactiveResumeConfig,
    find_config_file,
    load_config,
)


@pytest.fixture
def temp_config_file():
    config_data = {
        "ollama": {
            "endpoint": "http://localhost:11434",
            "model": "llama3.2",
            "cloud": False,
            "debug": False,
            "api_key": "",
        },
        "resume": {"endpoint": "http://localhost:3000", "api_key": "test-key"},
        "output": {"directory": "generated"},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config_data, f)
        yield Path(f.name)
    Path(f.name).unlink()


class TestOllamaConfig:
    def test_default_values(self):
        config = OllamaConfig()
        assert config.endpoint == "http://localhost:11434"
        assert config.model == "llama3.2"
        assert config.cloud is False
        assert config.debug is False
        assert config.api_key == ""

    def test_custom_values(self):
        config = OllamaConfig(
            endpoint="https://api.ollama.ai",
            model="codellama",
            cloud=True,
            debug=True,
            api_key="test-key",
        )
        assert config.endpoint == "https://api.ollama.ai"
        assert config.model == "codellama"
        assert config.cloud is True
        assert config.debug is True
        assert config.api_key == "test-key"

    def test_dataclass_immutability(self):
        config = OllamaConfig()
        config.endpoint = "http://custom.com"
        assert config.endpoint == "http://custom.com"


class TestReactiveResumeConfig:
    def test_default_values(self):
        config = ReactiveResumeConfig()
        assert config.endpoint == "http://localhost:3000"
        assert config.api_key == ""

    def test_custom_values(self):
        config = ReactiveResumeConfig(endpoint="https://resume.example.com", api_key="my-key")
        assert config.endpoint == "https://resume.example.com"
        assert config.api_key == "my-key"


class TestOutputConfig:
    def test_default_values(self):
        config = OutputConfig()
        assert config.directory == "generated"


class TestConfig:
    def test_default_values(self):
        config = Config()
        assert config.ollama.endpoint == "http://localhost:11434"
        assert config.resume.endpoint == "http://localhost:3000"
        assert config.output.directory == "generated"

    def test_from_dict_minimal(self):
        config = Config.from_dict({})
        assert config.ollama.model == "llama3.2"
        assert config.resume.api_key == ""

    def test_from_dict_full(self):
        data = {
            "ollama": {
                "endpoint": "http://custom.com",
                "model": "custom-model",
                "cloud": True,
                "api_key": "key",
            },
            "resume": {"endpoint": "http://custom-resume.com", "api_key": "resume-key"},
            "output": {"directory": "custom-output"},
        }
        config = Config.from_dict(data)
        assert config.ollama.endpoint == "http://custom.com"
        assert config.ollama.model == "custom-model"
        assert config.resume.api_key == "resume-key"
        assert config.output.directory == "custom-output"

    def test_from_file(self, temp_config_file):
        config = Config.from_file(str(temp_config_file))
        assert config.ollama.model == "llama3.2"
        assert config.resume.api_key == "test-key"


class TestFindConfigFile:
    def test_raises_if_not_found(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("FAST_APP_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        with pytest.raises(FileNotFoundError):
            find_config_file()

    def test_uses_cli_path_if_provided(self, temp_config_file):
        result = find_config_file(cli_path=str(temp_config_file))
        assert result == temp_config_file

    def test_raises_if_cli_path_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            find_config_file(cli_path="/nonexistent/config.json")
        assert "Config file not found" in str(exc_info.value)


class TestLoadConfig:
    def test_loads_from_file(self, temp_config_file):
        config = load_config(str(temp_config_file))
        assert config.resume.api_key == "test-key"
        assert config.ollama.model == "llama3.2"

    def test_load_config_with_cli_path(self, temp_config_file):
        config = load_config(str(temp_config_file))
        assert isinstance(config, Config)
        assert isinstance(config.ollama, OllamaConfig)
        assert isinstance(config.resume, ReactiveResumeConfig)

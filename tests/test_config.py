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


class TestOllamaConfig:
    def test_default_values(self):
        config = OllamaConfig()
        assert config.endpoint == "http://localhost:11434"
        assert config.model == "llama3.2"
        assert config.cloud is False
        assert config.api_key == ""

    def test_custom_values(self):
        config = OllamaConfig(
            endpoint="https://api.ollama.ai",
            model="codellama",
            cloud=True,
            api_key="test-key",
        )
        assert config.endpoint == "https://api.ollama.ai"
        assert config.model == "codellama"
        assert config.cloud is True
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
        assert config.reactive_resume.endpoint == "http://localhost:3000"
        assert config.output.directory == "generated"

    def test_from_dict_minimal(self):
        config = Config.from_dict({})
        assert config.ollama.model == "llama3.2"
        assert config.reactive_resume.api_key == ""

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
        assert config.reactive_resume.api_key == "resume-key"
        assert config.output.directory == "custom-output"

    def test_from_file(self):
        config_data = {
            "ollama": {
                "endpoint": "http://localhost:11434",
                "model": "llama3.2",
                "cloud": False,
                "debug": False,
                "api_key": "test-key",
            },
            "resume": {"endpoint": "http://localhost:3000", "api_key": "test-key"},
            "output": {"directory": "generated"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config = Config.from_file(temp_path)
            assert config.ollama.model == "llama3.2"
            assert config.reactive_resume.api_key == "test-key"
        finally:
            Path(temp_path).unlink()


class TestFindConfigFile:
    def test_raises_if_not_found(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("FAST_APP_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

        with pytest.raises(FileNotFoundError):
            find_config_file()

    def test_uses_cli_path_if_provided(self):
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"ollama": {}, "resume": {}}, f)
            temp_path = f.name

        try:
            find_config_file(cli_path=temp_path)
            assert Path(temp_path).exists()
        finally:
            Path(temp_path).unlink()

    def test_raises_if_cli_path_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            find_config_file(cli_path="/nonexistent/config.json")
        assert "Config file not found" in str(exc_info.value)


class TestLoadConfig:
    def test_loads_from_file(self):
        config_data = {
            "ollama": {
                "endpoint": "http://localhost:11434",
                "model": "llama3.2",
                "cloud": False,
                "debug": False,
                "api_key": "test-key",
            },
            "resume": {"endpoint": "http://localhost:3000", "api_key": "test-key"},
            "output": {"directory": "generated"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert config.ollama.model == "llama3.2"
            assert config.reactive_resume.api_key == "test-key"
        finally:
            Path(temp_path).unlink()

    def test_load_config_with_cli_path(self):
        config_data = {
            "ollama": {
                "endpoint": "http://localhost:11434",
                "model": "llama3.2",
                "cloud": False,
                "debug": False,
                "api_key": "test-key",
            },
            "resume": {"endpoint": "http://localhost:3000", "api_key": "test-key"},
            "output": {"directory": "generated"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            config = load_config(temp_path)
            assert isinstance(config, Config)
            assert isinstance(config.ollama, OllamaConfig)
            assert isinstance(config.reactive_resume, ReactiveResumeConfig)
        finally:
            Path(temp_path).unlink()

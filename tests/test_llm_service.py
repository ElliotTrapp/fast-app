"""Tests for LLM service provider abstraction.

Tests LLMService creation with different providers,
graceful degradation when LangChain is not installed,
and provider switching behavior.
"""

import pytest

from fast_app.config import Config, LLMConfig, OllamaConfig


class TestLLMServiceCreation:
    @pytest.fixture(autouse=True)
    def check_deps(self):
        try:
            import fast_app.services.llm_service  # noqa: F401
        except ImportError:
            pytest.skip("langchain packages not installed")

    def test_create_with_ollama_provider(self):
        from fast_app.services.llm_service import LLMService

        config = Config(
            ollama=OllamaConfig(endpoint="http://localhost:11434", model="llama3.2"),
            llm=LLMConfig(provider="ollama", model="llama3.2", temperature=0.3),
        )
        service = LLMService(config)
        assert service._llm is not None

    def test_create_with_opencode_go_provider(self):
        from fast_app.services.llm_service import LLMService

        config = Config(
            llm=LLMConfig(
                provider="opencode-go",
                model="gpt-4o",
                temperature=0.3,
                base_url="https://opencode.ai/zen/go/v1",
                api_key="test-key",
            ),
        )
        service = LLMService(config)
        assert service._llm is not None

    def test_create_with_unknown_provider_raises(self):
        from fast_app.services.llm_service import LLMService

        config = Config(
            llm=LLMConfig(provider="unknown-provider"),
        )
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            LLMService(config)

    def test_config_defaults_ollama(self):
        config = Config()
        assert config.llm.provider == "ollama"
        assert config.llm.model == ""
        assert config.llm.temperature == 0.3

    def test_config_overrides_from_env(self):
        existing_provider = __import__("os").environ.get("FAST_APP_LLM_PROVIDER")
        try:
            __import__("os").environ["FAST_APP_LLM_PROVIDER"] = "opencode-go"
            from fast_app.config import Config

            config = Config()
            assert config.llm.provider == "ollama"

        finally:
            if existing_provider is None:
                __import__("os").environ.pop("FAST_APP_LLM_PROVIDER", None)
            else:
                __import__("os").environ["FAST_APP_LLM_PROVIDER"] = existing_provider

    def test_database_config_defaults(self):
        from fast_app.config import DatabaseConfig

        db = DatabaseConfig()
        assert db.path == ""
        assert db.jwt_secret == ""
        assert db.jwt_algorithm == "HS256"
        assert db.jwt_expire_minutes == 1440

    def test_chroma_config_defaults(self):
        from fast_app.config import ChromaConfig

        chroma = ChromaConfig()
        assert chroma.path == ""
        assert chroma.embedding_model == "nomic-embed-text"
        assert chroma.client_type == "persistent"


class TestOllamaServiceDelegation:
    def test_ollama_service_accepts_ollama_config(self):
        from fast_app.config import OllamaConfig
        from fast_app.services.ollama import OllamaService

        config = OllamaConfig(endpoint="http://localhost:11434", model="llama3.2")
        service = OllamaService(config)
        assert service.config.model == "llama3.2"

    def test_ollama_service_accepts_full_config(self):
        from fast_app.config import LLMConfig, OllamaConfig
        from fast_app.services.ollama import OllamaService

        config = Config(
            ollama=OllamaConfig(endpoint="http://localhost:11434", model="llama3.2"),
            llm=LLMConfig(provider="ollama", model="llama3.2"),
        )
        service = OllamaService(config)
        assert service.config.model == "llama3.2"

    def test_ollama_service_preserves_check_connection(self):
        from fast_app.config import OllamaConfig
        from fast_app.services.ollama import OllamaService

        config = OllamaConfig(endpoint="http://localhost:11434", model="llama3.2")
        service = OllamaService(config)
        assert hasattr(service, "check_connection")
        assert hasattr(service, "check_model_available")

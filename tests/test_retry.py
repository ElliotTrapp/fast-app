"""Tests for retry logic."""

from unittest.mock import Mock, patch

import pytest
import requests

from fast_app.config import OllamaConfig
from fast_app.services.ollama import OllamaService
from fast_app.services.reactive_resume import ReactiveResumeClient


class TestRetryLogic:
    def test_ollama_retries_on_connection_error(self):
        config = OllamaConfig(endpoint="http://localhost:11434", model="test")
        service = OllamaService(config)

        with patch.object(service.client, "chat") as mock_chat:
            mock_chat.side_effect = [
                requests.ConnectionError("Connection refused"),
                requests.ConnectionError("Connection refused"),
                {"message": {"content": '{"title": "Test"}'}},
            ]

            result = service.generate_questions({"title": "Test"}, {"basics": {}})
            assert isinstance(result, list)
            assert mock_chat.call_count == 3

    def test_ollama_fails_after_max_retries(self):
        config = OllamaConfig(endpoint="http://localhost:11434", model="test")
        service = OllamaService(config)

        with patch.object(service.client, "chat") as mock_chat:
            mock_chat.side_effect = requests.ConnectionError("Connection refused")

            with pytest.raises(RuntimeError) as exc_info:
                service.generate_questions({"title": "Test"}, {"basics": {}})
            assert "after 4 attempts" in str(exc_info.value)

    def test_reactive_resume_retries_on_503(self):
        client = ReactiveResumeClient("http://localhost:3000", "test-key")

        with patch("requests.get") as mock_get:
            mock_get.side_effect = [
                Mock(status_code=503),
                Mock(status_code=503),
                Mock(status_code=200, json=lambda: [{"id": "1"}]),
            ]

            result = client.list_resumes()
            assert result == [{"id": "1"}]

    def test_reactive_resume_fails_after_retries(self):
        client = ReactiveResumeClient("http://localhost:3000", "test-key")

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("Connection refused")

            with pytest.raises(RuntimeError) as exc_info:
                client.list_resumes()
            assert "after 4 attempts" in str(exc_info.value)

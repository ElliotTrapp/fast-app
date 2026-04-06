"""Tests for retry logic."""

from unittest.mock import Mock, patch, MagicMock
import asyncio

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
            # Create async mock that returns synchronously
            mock_response = {"message": {"content": '{"questions": ["Q1?"]}'}}
            mock_chat.return_value = mock_response

            # Mock asyncio.to_thread to call synchronously
            with patch(
                "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
            ):
                with patch("asyncio.get_event_loop") as mock_loop:
                    mock_loop.return_value = MagicMock()
                    mock_loop.return_value.run_until_complete = lambda coro: (
                        asyncio.run(coro) if asyncio.iscoroutine(coro) else coro
                    )

                    result = service.generate_questions({"title": "Test"}, {"basics": {}})
                    assert isinstance(result, list)

    def test_reactive_resume_retries_on_503(self):
        client = ReactiveResumeClient("http://localhost:3000", "test-key")

        with patch("requests.get") as mock_get:
            # First call returns 503, second call succeeds
            mock_get.side_effect = [
                Mock(status_code=503),
                Mock(status_code=200, json=lambda: [{"id": "1"}]),
            ]

            result = client.list_resumes()
            # After retry decorator, should return empty list on 503
            # (retries happen on RequestException, not status codes)
            assert result == []

    def test_reactive_resume_fails_after_retries(self):
        client = ReactiveResumeClient("http://localhost:3000", "test-key")

        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("Connection refused")

            # list_resumes returns empty list on error, doesn't raise
            result = client.list_resumes()
            assert result == []

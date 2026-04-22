"""Tests for Job Extractor service."""

import json
from unittest.mock import Mock, patch

import pytest

from fast_app.services.job_extractor import JobExtractor


@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def extractor(mock_client):
    return JobExtractor(mock_client, "test-model")


class TestJobExtractorInit:
    def test_stores_client_and_model(self, mock_client):
        extractor = JobExtractor(mock_client, "codellama")
        assert extractor.client == mock_client
        assert extractor.model == "codellama"


class TestStripMarkdownJson:
    def test_strips_json_block(self, extractor):
        result = extractor._strip_markdown_json('```json\n{"key": "value"}\n```')
        assert "key" in result and "value" in result
        assert "```" not in result

    def test_strips_code_block(self, extractor):
        result = extractor._strip_markdown_json('```\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_returns_unchanged_if_no_block(self, extractor):
        content = '{"key": "value"}'
        result = extractor._strip_markdown_json(content)
        assert result == content

    def test_handles_whitespace(self, extractor):
        result = extractor._strip_markdown_json('  ```json\n  {"key": "value"}\n  ```  ')
        assert "key" in result and "value" in result


class TestExtractFromUrlIntegration:
    """Integration tests that test the sync wrapper with actual async execution."""

    @pytest.mark.integration
    def test_extracts_job_data_real_async(self, mock_client):
        """Test full extraction flow with real asyncio (integration test)."""

        # Setup mocks
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Software Engineer at Acme"
        mock_fetch_result.content = "We are hiring..."

        # Mock asyncio.to_thread to call synchronously
        async def mock_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch(
            "asyncio.to_thread", side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
        ):
            mock_client.web_fetch.return_value = mock_fetch_result
            mock_client.chat.return_value = {
                "message": {
                    "content": json.dumps(
                        {
                            "title": "Software Engineer",
                            "company": "Acme",
                            "location": "San Francisco, CA",
                        }
                    )
                }
            }

            extractor = JobExtractor(mock_client, "test")
            result = extractor.extract_from_url("https://example.com/job/123")

        # Verify results
        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme"
        assert result["location"] == "San Francisco, CA"
        assert "id" in result  # ID field should exist
        assert "job_url" in result  # URL field should exist

    @pytest.mark.integration
    def test_calls_web_fetch_real_async(self, mock_client):
        """Test that web_fetch is called with correct URL."""
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor = JobExtractor(mock_client, "test")
        extractor.extract_from_url("https://example.com/job/123")

        mock_client.web_fetch.assert_called_once_with("https://example.com/job/123")

    def test_raises_on_fetch_error(self, mock_client):
        """Test that fetch errors are properly handled."""
        import requests

        mock_client.web_fetch.side_effect = requests.RequestException("Connection failed")

        extractor = JobExtractor(mock_client, "test")

        with pytest.raises(RuntimeError) as exc_info:
            extractor.extract_from_url("https://example.com/job/123")

        assert "Failed to extract job data" in str(exc_info.value)

    @pytest.mark.integration
    def test_passes_format_schema(self, mock_client):
        """Test that JobData schema is passed to LLM."""
        from fast_app.models import JobData

        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor = JobExtractor(mock_client, "test")
        extractor.extract_from_url("https://example.com/job/123")

        call_args = mock_client.chat.call_args
        assert "format" in call_args[1]
        assert call_args[1]["format"] == JobData.model_json_schema()

"""Tests for Job Extractor service."""

from unittest.mock import Mock

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


class TestExtractFromUrl:
    def test_extracts_job_data(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Software Engineer at Acme"
        mock_fetch_result.content = "We are hiring a software engineer..."

        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {
            "message": {
                "content": '{"title": "Software Engineer", "company": "Acme", "location": "San Francisco, CA"}'
            }
        }

        result = extractor.extract_from_url("https://example.com/job/123")

        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme"
        assert result["job_url"] == "https://example.com/job/123"
        assert "id" in result

    def test_calls_web_fetch(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor.extract_from_url("https://example.com/job/123")

        mock_client.web_fetch.assert_called_once_with("https://example.com/job/123")

    def test_generates_hash_id(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        result1 = extractor.extract_from_url("https://example.com/job/123")
        result2 = extractor.extract_from_url("https://example.com/job/123")

        assert result1["id"] == result2["id"]
        assert len(result1["id"]) == 12

    def test_extracts_site_from_url(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        result = extractor.extract_from_url("https://linkedin.com/jobs/view/123")
        assert result["site"] == "linkedin.com"

    def test_strips_markdown_json(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '```json\\n{"title": "Job"}\\n```'}}

        result = extractor.extract_from_url("https://example.com/job/123")
        assert result["title"] == "Job"

    def test_raises_on_fetch_error(self, extractor, mock_client):
        mock_client.web_fetch.side_effect = Exception("Connection failed")

        with pytest.raises(RuntimeError) as exc_info:
            extractor.extract_from_url("https://example.com/job/123")
        assert "Failed to fetch URL" in str(exc_info.value)

    def test_raises_on_parse_error(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": "invalid json"}}

        with pytest.raises(RuntimeError) as exc_info:
            extractor.extract_from_url("https://example.com/job/123")
        assert "Failed to extract" in str(exc_info.value)

    def test_passes_format_schema(self, extractor, mock_client):
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor.extract_from_url("https://example.com/job/123")

        call_args = mock_client.chat.call_args
        assert "format" in call_args[1]


class TestStripMarkdownJson:
    def test_strips_json_block(self, extractor):
        result = extractor._strip_markdown_json('```json\\n{"key": "value"}\\n```')
        assert result == '{"key": "value"}'

    def test_strips_code_block(self, extractor):
        result = extractor._strip_markdown_json('```\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_returns_unchanged_if_no_block(self, extractor):
        content = '{"key": "value"}'
        result = extractor._strip_markdown_json(content)
        assert result == content

    def test_handles_whitespace(self, extractor):
        result = extractor._strip_markdown_json('  ```json\\n  {"key": "value"}\\n  ```  ')
        assert result == '{"key": "value"}'

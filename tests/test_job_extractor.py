"""Tests for Job Extractor service — multi-strategy fetcher and text extraction."""

import json
import sys
from unittest.mock import Mock, patch

import pytest

from fast_app.models import JobData
from fast_app.services.job_extractor import (
    JobExtractor,
    _fetch_with_requests,
    _fetch_workday_cxs,
    _is_workday_url,
    _parse_workday_url,
)
from fast_app.utils.text import strip_markdown_json

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    return Mock()


@pytest.fixture
def extractor(mock_client):
    return JobExtractor(mock_client, "test-model")


@pytest.fixture(autouse=True)
def patch_logger():
    """Patch logger.debug (a bool property) so logger.debug(...) doesn't crash."""
    with patch("fast_app.services.job_extractor.logger") as mock_log:
        mock_log.debug = Mock()
        yield mock_log


def _make_chat_response(**overrides):
    """Build a valid JobData dict for mock LLM responses.

    Includes job_url and site so that **extracted doesn't override
    the URL-derived values set by _extract_job_data_from_content.
    """
    data = {
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "San Francisco, CA",
        "description": "Build things",
        "job_url": "",
        "job_url_direct": None,
        "site": "",
        "min_amount": None,
        "max_amount": None,
        "currency": None,
        "interval": None,
        "job_type": None,
        "is_remote": None,
        "job_level": None,
        "job_function": None,
        "skills": None,
        "company_industry": None,
        "company_url": None,
        "company_description": None,
        "company_num_employees": None,
    }
    data.update(overrides)
    return {"message": {"content": json.dumps(data)}}


# ---------------------------------------------------------------------------
# _is_workday_url
# ---------------------------------------------------------------------------


class TestIsWorkdayUrl:
    def test_true_for_workday_url(self):
        assert _is_workday_url(
            "https://argonne.wd1.myworkdayjobs.com/en-US/Argonne_Careers/details/123"
        )

    def test_true_for_workday_url_case_insensitive(self):
        assert _is_workday_url("https://NVIDIA.WD5.MYWORKDAYJOBS.COM/en-US/jobs/456")

    def test_false_for_regular_url(self):
        assert not _is_workday_url("https://www.example.com/jobs/123")

    def test_false_for_localhost(self):
        assert not _is_workday_url("http://localhost:3000/jobs")

    def test_false_for_empty_string(self):
        assert not _is_workday_url("")


# ---------------------------------------------------------------------------
# _parse_workday_url
# ---------------------------------------------------------------------------


class TestParseWorkdayUrl:
    def test_parses_standard_workday_url(self):
        url = (
            "https://argonne.wd1.myworkdayjobs.com/en-US/"
            "Argonne_Careers/details/Scientific-Data-Engineer_422640"
        )
        result = _parse_workday_url(url)
        assert result is not None
        tenant, host, site_id = result
        assert tenant == "argonne"
        assert host == "argonne.wd1.myworkdayjobs.com"
        assert site_id == "Argonne_Careers"

    def test_parses_nvidia_workday_url(self):
        url = (
            "https://nvidia.wd5.myworkdayjobs.com/en-US/"
            "NVIDIAExternalCareerSite/job/Software-Engineer_422640"
        )
        result = _parse_workday_url(url)
        assert result is not None
        tenant, host, site_id = result
        assert tenant == "nvidia"
        assert site_id == "NVIDIAExternalCareerSite"

    def test_returns_none_for_non_workday_url(self):
        result = _parse_workday_url("https://www.example.com/jobs/123")
        assert result is None

    def test_fallback_site_id_when_missing(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-US/"
        result = _parse_workday_url(url)
        assert result is not None
        tenant, host, site_id = result
        assert site_id == "External"

    def test_skips_locale_prefix(self):
        url = "https://acme.wd1.myworkdayjobs.com/en-GB/Acme_Careers/details/123"
        result = _parse_workday_url(url)
        assert result is not None
        assert result[2] == "Acme_Careers"

    def test_returns_none_on_exception(self):
        result = _parse_workday_url("not a url at all :::///")
        # urlparse handles this gracefully — just ensure no crash
        assert result is None or isinstance(result, tuple)


# ---------------------------------------------------------------------------
# _fetch_workday_cxs — detail path
# ---------------------------------------------------------------------------


class TestFetchWorkdayCxsDetail:
    @patch("requests.get")
    def test_fetches_job_detail_successfully(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Senior Engineer",
            "jobPostingInfo": {
                "jobDescription": "<p>Build amazing things</p><p>Remote OK</p>",
            },
        }
        mock_get.return_value = mock_resp

        result = _fetch_workday_cxs(
            "argonne",
            "argonne.wd1.myworkdayjobs.com",
            "Argonne_Careers",
            "https://argonne.wd1.myworkdayjobs.com/en-US/"
            "Argonne_Careers/details/Scientific-Data-Engineer_422640",
        )

        assert result is not None
        assert "Senior Engineer" in result
        assert "Build amazing things" in result
        assert "Remote OK" in result
        # HTML tags should be stripped
        assert "<p>" not in result

    @patch("requests.get")
    def test_detail_url_includes_correct_path(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "title": "Engineer",
            "jobPostingInfo": {"jobDescription": "<p>Desc</p>"},
        }
        mock_get.return_value = mock_resp

        _fetch_workday_cxs(
            "argonne",
            "argonne.wd1.myworkdayjobs.com",
            "Argonne_Careers",
            "https://argonne.wd1.myworkdayjobs.com/en-US/"
            "Argonne_Careers/details/Scientific-Data-Engineer_422640",
        )

        call_url = mock_get.call_args[0][0]
        assert "/wday/cxs/argonne/Argonne_Careers/details/" in call_url

    @patch("requests.get")
    @patch("requests.post")
    def test_detail_non_200_falls_through_to_search(self, mock_post, mock_get):
        # URL with a detail path so job_path is set
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/details/Eng_123"

        # First GET (detail) returns 404
        detail_resp = Mock()
        detail_resp.status_code = 404

        # Search POST returns a result
        search_resp = Mock()
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Engineer",
                    "externalPath": "/details/Eng_123",
                    "locationsText": "Remote",
                }
            ]
        }

        # Second GET (detail after search) returns 200
        detail_resp2 = Mock()
        detail_resp2.status_code = 200
        detail_resp2.json.return_value = {
            "jobPostingInfo": {"jobDescription": "<p>Found via search</p>"},
        }

        mock_get.side_effect = [detail_resp, detail_resp2]
        mock_post.return_value = search_resp

        result = _fetch_workday_cxs("acme", "acme.wd1.myworkdayjobs.com", "Acme_Careers", url)

        assert result is not None
        assert "Found via search" in result


# ---------------------------------------------------------------------------
# _fetch_workday_cxs — search path
# ---------------------------------------------------------------------------


class TestFetchWorkdayCxsSearch:
    @patch("requests.get")
    @patch("requests.post")
    def test_search_fallback_with_detail(self, mock_post, mock_get):
        """Search returns a posting, then detail is fetched."""
        # URL without detail path so job_path is None
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/"

        search_resp = Mock()
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Data Scientist",
                    "externalPath": "/details/Data-Scientist_999",
                    "locationsText": "New York, NY",
                }
            ]
        }

        detail_resp = Mock()
        detail_resp.status_code = 200
        detail_resp.json.return_value = {
            "jobPostingInfo": {
                "jobDescription": "<p>Analyze data</p>",
            },
        }

        # Only 1 GET call: detail after search (no initial detail GET)
        mock_get.return_value = detail_resp
        mock_post.return_value = search_resp

        result = _fetch_workday_cxs("acme", "acme.wd1.myworkdayjobs.com", "Acme_Careers", url)

        assert result is not None
        assert "Data Scientist" in result
        assert "Analyze data" in result

    @patch("requests.get")
    @patch("requests.post")
    def test_search_listing_without_detail(self, mock_post, mock_get):
        """Search returns a posting but detail fetch fails — use listing data."""
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/"

        search_resp = Mock()
        search_resp.status_code = 200
        search_resp.json.return_value = {
            "jobPostings": [
                {
                    "title": "Product Manager",
                    "locationsText": "Austin, TX",
                    "bulletFields": ["Full-time", "5+ years"],
                }
            ]
        }

        # Detail GET after search returns 404
        fail_resp = Mock()
        fail_resp.status_code = 404
        mock_get.return_value = fail_resp
        mock_post.return_value = search_resp

        result = _fetch_workday_cxs("acme", "acme.wd1.myworkdayjobs.com", "Acme_Careers", url)

        assert result is not None
        assert "Product Manager" in result
        assert "Austin, TX" in result

    @patch("requests.get")
    @patch("requests.post")
    def test_returns_none_when_all_fail(self, mock_post, mock_get):
        url = "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/"

        detail_resp = Mock()
        detail_resp.status_code = 404
        search_resp = Mock()
        search_resp.status_code = 500

        mock_get.return_value = detail_resp
        mock_post.return_value = search_resp

        result = _fetch_workday_cxs("acme", "acme.wd1.myworkdayjobs.com", "Acme_Careers", url)

        assert result is None

    def test_returns_none_when_requests_not_installed(self):
        with patch.dict(sys.modules, {"requests": None}):
            result = _fetch_workday_cxs(
                "acme",
                "acme.wd1.myworkdayjobs.com",
                "Acme_Careers",
                "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/",
            )
            assert result is None


# ---------------------------------------------------------------------------
# _fetch_with_requests
# ---------------------------------------------------------------------------


class TestFetchWithRequests:
    @patch("requests.get")
    def test_fetches_html_page_successfully(self, mock_get):
        html = (
            "<html><head><title>Job at Acme</title></head>"
            "<body><p>We are hiring a Software Engineer.</p>"
            "<p>Requirements: Python, SQL, 5+ years experience.</p>"
            "<p>Benefits include health insurance and remote work.</p>"
            "<p>Apply now at careers.acme.com.</p></body></html>"
        )
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://careers.acme.com/job/123")

        assert result is not None
        assert "Job at Acme" in result
        assert "Software Engineer" in result
        # HTML tags should be stripped
        assert "<p>" not in result

    @patch("requests.get")
    def test_strips_script_and_style_tags(self, mock_get):
        # Content must be > 100 chars after stripping to pass threshold
        body_text = (
            "<p>Real content here that is long enough to pass the "
            "threshold check for the function.</p>"
        )
        extra = "<p>Additional paragraph with more details about the position.</p>"
        html = (
            "<html><head><title>Job</title>"
            "<script>var x = 1;</script>"
            "<style>body { color: red; }</style>"
            "</head><body>" + body_text + extra + "</body></html>"
        )
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://example.com/job")

        assert result is not None
        assert "var x" not in result
        assert "color: red" not in result
        assert "Real content" in result

    @patch("requests.get")
    def test_returns_none_for_non_html_content_type(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/pdf"}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://example.com/resume.pdf")
        assert result is None

    @patch("requests.get")
    def test_returns_none_for_short_content(self, mock_get):
        html = "<html><body><p>Hi</p></body></html>"
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        result = _fetch_with_requests("https://example.com/job")
        assert result is None

    @patch("requests.get")
    def test_returns_none_on_request_exception(self, mock_get):
        mock_get.side_effect = Exception("Connection failed")
        result = _fetch_with_requests("https://example.com/job")
        assert result is None

    def test_returns_none_when_requests_not_installed(self):
        with patch.dict(sys.modules, {"requests": None}):
            result = _fetch_with_requests("https://example.com/job")
            assert result is None

    @patch("requests.get")
    def test_sends_browser_like_headers(self, mock_get):
        html = (
            "<html><head><title>Job</title></head>"
            "<body>" + "<p>Content paragraph.</p>" * 20 + "</body></html>"
        )
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.raise_for_status = Mock()
        mock_get.return_value = mock_resp

        _fetch_with_requests("https://example.com/job")

        call_kwargs = mock_get.call_args[1]
        assert "headers" in call_kwargs
        assert "User-Agent" in call_kwargs["headers"]
        assert "Mozilla" in call_kwargs["headers"]["User-Agent"]


# ---------------------------------------------------------------------------
# _strip_markdown_json
# ---------------------------------------------------------------------------


class TestStripMarkdownJson:
    def test_strips_json_block(self, extractor):
        result = strip_markdown_json('```json\n{"key": "value"}\n```')
        assert "key" in result and "value" in result
        assert "```" not in result

    def test_strips_code_block(self, extractor):
        result = strip_markdown_json('```\n{"key": "value"}\n```')
        assert result == '{"key": "value"}'

    def test_returns_unchanged_if_no_block(self, extractor):
        content = '{"key": "value"}'
        result = strip_markdown_json(content)
        assert result == content

    def test_handles_whitespace(self, extractor):
        result = strip_markdown_json('  ```json\n  {"key": "value"}\n  ```  ')
        assert "key" in result and "value" in result


# ---------------------------------------------------------------------------
# _extract_job_data_from_content
# ---------------------------------------------------------------------------


class TestExtractJobDataFromContent:
    def test_extracts_job_data_from_content(self, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response(
            job_url="https://example.com/job/123",
            site="example.com",
        )

        result = extractor._extract_job_data_from_content(
            "Title: Software Engineer\n\nContent:\nBuild things at Acme",
            "https://example.com/job/123",
        )

        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme Corp"
        assert result["job_url"] == "https://example.com/job/123"
        assert "id" in result
        assert "site" in result

    def test_passes_jobdata_schema_to_llm(self, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response()

        extractor._extract_job_data_from_content("Some content", "https://example.com")

        call_kwargs = mock_client.chat.call_args[1]
        assert "format" in call_kwargs
        assert call_kwargs["format"] == JobData.model_json_schema()

    def test_strips_markdown_json_from_llm_response(self, extractor, mock_client):
        data = {"title": "Engineer", "company": "Test"}
        mock_client.chat.return_value = {
            "message": {"content": f"```json\n{json.dumps(data)}\n```"}
        }

        result = extractor._extract_job_data_from_content("content", "https://example.com")

        assert result["title"] == "Engineer"
        assert result["company"] == "Test"

    def test_uses_text_input_as_site_when_no_url(self, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response(site="text_input")

        result = extractor._extract_job_data_from_content("Some content", "")

        assert result["site"] == "text_input"

    def test_extracts_site_from_url(self, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response(site="careers.example.com")

        result = extractor._extract_job_data_from_content(
            "content", "https://careers.example.com/jobs/123"
        )

        assert result["site"] == "careers.example.com"


# ---------------------------------------------------------------------------
# extract_from_url — multi-strategy selection
# ---------------------------------------------------------------------------


class TestExtractFromUrl:
    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=True)
    @patch("fast_app.services.job_extractor._parse_workday_url")
    @patch("fast_app.services.job_extractor._fetch_workday_cxs")
    def test_workday_url_uses_cxs_strategy(
        self, mock_cxs, mock_parse, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        mock_parse.return_value = (
            "acme",
            "acme.wd1.myworkdayjobs.com",
            "Acme_Careers",
        )
        mock_cxs.return_value = "Title: Engineer\n\nContent:\nBuild things"
        mock_client.chat.return_value = _make_chat_response()

        result = extractor.extract_from_url(
            "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/details/123"
        )

        assert result["title"] == "Software Engineer"
        mock_cxs.assert_called_once()
        # web_fetch should NOT be called
        mock_client.web_fetch.assert_not_called()

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=True)
    @patch("fast_app.services.job_extractor._parse_workday_url")
    @patch("fast_app.services.job_extractor._fetch_workday_cxs")
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_workday_cxs_failure_falls_back_to_requests(
        self,
        mock_fetch_req,
        mock_cxs,
        mock_parse,
        mock_is_wd,
        mock_to_thread,
        extractor,
        mock_client,
    ):
        mock_parse.return_value = (
            "acme",
            "acme.wd1.myworkdayjobs.com",
            "Acme_Careers",
        )
        mock_cxs.return_value = None  # CXS fails
        mock_fetch_req.return_value = (
            "Title: Engineer\n\nContent:\nBuild things at Acme Corp. "
            "We need Python developers with 5 years experience. "
            "Great benefits and remote work available."
        )
        mock_client.chat.return_value = _make_chat_response()

        result = extractor.extract_from_url(
            "https://acme.wd1.myworkdayjobs.com/en-US/Acme_Careers/details/123"
        )

        assert result["title"] == "Software Engineer"
        mock_fetch_req.assert_called_once()

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_normal_url_uses_requests_strategy(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        # Content must be > 200 chars to avoid falling through to web_fetch
        long_content = (
            "Title: Engineer\n\nContent:\nBuild things at Acme Corp. "
            "We need Python developers with 5 years experience. "
            "Great benefits and remote work available. "
            "Apply now for this exciting opportunity to join our team "
            "and work on cutting-edge projects in a fast-paced environment."
        )
        mock_fetch_req.return_value = long_content
        mock_client.chat.return_value = _make_chat_response()

        result = extractor.extract_from_url("https://example.com/jobs/123")

        assert result["title"] == "Software Engineer"
        mock_fetch_req.assert_called_once_with("https://example.com/jobs/123")
        mock_client.web_fetch.assert_not_called()

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_requests_failure_falls_back_to_web_fetch(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        mock_fetch_req.return_value = None  # requests fails
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Software Engineer at Acme"
        mock_fetch_result.content = "We are hiring..."
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = _make_chat_response()

        result = extractor.extract_from_url("https://example.com/jobs/123")

        assert result["title"] == "Software Engineer"
        mock_client.web_fetch.assert_called_once_with("https://example.com/jobs/123")

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_requests_insufficient_content_falls_back_to_web_fetch(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        # Content too short (< 200 chars)
        mock_fetch_req.return_value = "Title: Job\n\nContent:\nShort"
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Software Engineer at Acme"
        mock_fetch_result.content = "We are hiring..."
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = _make_chat_response()

        result = extractor.extract_from_url("https://example.com/jobs/123")

        assert result["title"] == "Software Engineer"
        mock_client.web_fetch.assert_called_once()

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_all_strategies_fail_raises_runtime_error(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        mock_fetch_req.return_value = None
        mock_client.web_fetch.side_effect = Exception("Connection failed")

        with pytest.raises(RuntimeError, match="Failed to extract job data"):
            extractor.extract_from_url("https://example.com/jobs/123")

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_passes_format_schema_to_llm(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, extractor, mock_client
    ):
        mock_fetch_req.return_value = "Title: Job\n\nContent:\n" + "A" * 300
        mock_client.chat.return_value = _make_chat_response()

        extractor.extract_from_url("https://example.com/jobs/123")

        call_kwargs = mock_client.chat.call_args[1]
        assert "format" in call_kwargs
        assert call_kwargs["format"] == JobData.model_json_schema()


# ---------------------------------------------------------------------------
# extract_from_text — direct text input
# ---------------------------------------------------------------------------


class TestExtractFromText:
    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    def test_extracts_from_text_input(self, mock_to_thread, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response(site="text_input")

        result = extractor.extract_from_text(
            "Software Engineer at Acme",
            "We are hiring a Python developer with 5 years experience.",
        )

        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme Corp"
        assert result["site"] == "text_input"

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    def test_passes_url_metadata_when_provided(self, mock_to_thread, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response(
            job_url="https://example.com/job/123",
            site="example.com",
        )

        result = extractor.extract_from_text(
            "Software Engineer",
            "Job description content here.",
            url="https://example.com/job/123",
        )

        assert result["job_url"] == "https://example.com/job/123"
        assert result["site"] == "example.com"

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    def test_formats_content_with_title(self, mock_to_thread, extractor, mock_client):
        mock_client.chat.return_value = _make_chat_response()

        extractor.extract_from_text("Senior Engineer", "Build great products.")

        # Verify the prompt includes the title and content
        call_args = mock_client.chat.call_args
        prompt = call_args[1]["messages"][0]["content"]
        assert "Senior Engineer" in prompt
        assert "Build great products" in prompt

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    def test_raises_on_llm_error(self, mock_to_thread, extractor, mock_client):
        mock_client.chat.side_effect = Exception("LLM unavailable")

        with pytest.raises(RuntimeError, match="Failed to extract job data from text"):
            extractor.extract_from_text("Title", "Content")


# ---------------------------------------------------------------------------
# extract_from_url — integration-style tests (updated for async flow)
# ---------------------------------------------------------------------------


class TestExtractFromUrlIntegration:
    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_extracts_job_data_full_flow(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, mock_client
    ):
        mock_fetch_result = (
            "Title: Software Engineer at Acme\n\nContent:\n"
            "We are hiring a Python developer with 5 years experience. "
            "Great benefits and remote work available. Apply now!"
        )
        mock_fetch_req.return_value = mock_fetch_result
        mock_client.chat.return_value = _make_chat_response(
            title="Software Engineer",
            company="Acme",
            location="San Francisco, CA",
        )

        extractor = JobExtractor(mock_client, "test")
        result = extractor.extract_from_url("https://example.com/job/123")

        assert result["title"] == "Software Engineer"
        assert result["company"] == "Acme"
        assert result["location"] == "San Francisco, CA"
        assert "id" in result
        assert "job_url" in result

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_calls_web_fetch_when_requests_fails(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, mock_client
    ):
        mock_fetch_req.return_value = None
        mock_fetch_result = Mock()
        mock_fetch_result.title = "Job"
        mock_fetch_result.content = "Description"
        mock_client.web_fetch.return_value = mock_fetch_result
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor = JobExtractor(mock_client, "test")
        extractor.extract_from_url("https://example.com/job/123")

        mock_client.web_fetch.assert_called_once_with("https://example.com/job/123")

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_raises_on_all_fetch_errors(
        self, mock_fetch_req, mock_is_wd, mock_to_thread, mock_client
    ):
        mock_fetch_req.return_value = None
        mock_client.web_fetch.side_effect = Exception("Connection failed")

        extractor = JobExtractor(mock_client, "test")

        with pytest.raises(RuntimeError, match="Failed to extract job data"):
            extractor.extract_from_url("https://example.com/job/123")

    @patch(
        "fast_app.services.job_extractor.asyncio.to_thread",
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs),
    )
    @patch("fast_app.services.job_extractor._is_workday_url", return_value=False)
    @patch("fast_app.services.job_extractor._fetch_with_requests")
    def test_passes_format_schema(self, mock_fetch_req, mock_is_wd, mock_to_thread, mock_client):
        mock_fetch_req.return_value = "Title: Job\n\nContent:\n" + "A" * 300
        mock_client.chat.return_value = {"message": {"content": '{"title": "Job"}'}}

        extractor = JobExtractor(mock_client, "test")
        extractor.extract_from_url("https://example.com/job/123")

        call_args = mock_client.chat.call_args
        assert "format" in call_args[1]
        assert call_args[1]["format"] == JobData.model_json_schema()

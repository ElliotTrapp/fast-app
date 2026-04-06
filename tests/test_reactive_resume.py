"""Integration tests for Reactive Resume API client with mocked responses."""

from unittest.mock import Mock, patch

import pytest
import requests

from fast_app.services.reactive_resume import ReactiveResumeClient


@pytest.fixture
def client():
    return ReactiveResumeClient("http://localhost:3000", "test-api-key")


class TestReactiveResumeClientInit:
    def test_strips_trailing_slash_from_endpoint(self):
        client = ReactiveResumeClient("http://localhost:3000/", "key")
        assert client.base_url == "http://localhost:3000"

    def test_sets_headers(self):
        client = ReactiveResumeClient("http://localhost:3000", "my-key")
        assert client.headers["Content-Type"] == "application/json"
        assert client.headers["x-api-key"] == "my-key"


class TestTestConnection:
    def test_returns_true_on_200(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200)
            assert client.test_connection() is True

    def test_returns_true_on_401(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=401)
            assert client.test_connection() is True

    def test_returns_true_on_302(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=302)
            assert client.test_connection() is True

    def test_returns_false_on_connection_error(self, client):
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Connection error")
            assert client.test_connection() is False


class TestListResumes:
    def test_returns_list_directly(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200, json=lambda: [{"id": "1", "title": "Resume 1"}]
            )
            result = client.list_resumes()
            assert result == [{"id": "1", "title": "Resume 1"}]

    def test_returns_data_field_from_dict(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: {"data": [{"id": "1"}]})
            result = client.list_resumes()
            assert result == [{"id": "1"}]

    def test_returns_resumes_field_from_dict(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: {"resumes": [{"id": "1"}]})
            result = client.list_resumes()
            assert result == [{"id": "1"}]

    def test_returns_empty_on_error(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=500)
            result = client.list_resumes()
            assert result == []

    def test_returns_empty_on_json_error(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=200, json=lambda: None)
            result = client.list_resumes()
            assert result == []


class TestGetResume:
    def test_returns_resume_on_success(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(
                status_code=200, json=lambda: {"id": "1", "title": "Resume"}
            )
            result = client.get_resume("1")
            assert result == {"id": "1", "title": "Resume"}

    def test_returns_none_on_404(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=404)
            result = client.get_resume("nonexistent")
            assert result is None

    def test_returns_none_on_error(self, client):
        with patch("requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=500)
            result = client.get_resume("1")
            assert result is None

    def test_returns_none_on_request_exception(self, client):
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.RequestException("Error")
            result = client.get_resume("1")
            assert result is None


class TestFindResumeByTitle:
    def test_returns_id_if_found(self, client):
        with patch.object(client, "list_resumes") as mock_list:
            mock_list.return_value = [
                {"id": "1", "title": "Resume 1"},
                {"id": "2", "title": "Resume 2"},
            ]
            result = client.find_resume_by_title("Resume 1")
            assert result == "1"

    def test_returns_none_if_not_found(self, client):
        with patch.object(client, "list_resumes") as mock_list:
            mock_list.return_value = [{"id": "1", "title": "Resume 1"}]
            result = client.find_resume_by_title("Nonexistent")
            assert result is None

    def test_handles_dict_format(self, client):
        with patch.object(client, "list_resumes") as mock_list:
            mock_list.return_value = [
                {"title": "Resume 1", "id": "abc"},
            ]
            result = client.find_resume_by_title("Resume 1")
            assert result == "abc"


class TestCreateResume:
    def test_creates_resume_with_title(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, json=lambda: "resume-id-123")
            result = client.create_resume("Software Engineer Resume")
            assert result == "resume-id-123"
            call_args = mock_post.call_args
            assert call_args[1]["json"]["name"] == "Software Engineer Resume"
            assert call_args[1]["json"]["tags"] == []

    def test_creates_resume_with_tags(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, json=lambda: "resume-id-123")
            result = client.create_resume("Resume", tags=["Acme"])
            assert result == "resume-id-123"
            call_args = mock_post.call_args
            assert call_args[1]["json"]["tags"] == ["Acme"]

    def test_generates_slug_from_title(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, json=lambda: "id")
            client.create_resume("Software Engineer at Company")
            call_args = mock_post.call_args
            assert "software-engineer-at-company" in call_args[1]["json"]["slug"]

    def test_truncates_long_slug(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, json=lambda: "id")
            client.create_resume("A" * 100)
            call_args = mock_post.call_args
            assert len(call_args[1]["json"]["slug"]) <= 50

    def test_raises_on_401(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=401)
            with pytest.raises(RuntimeError) as exc_info:
                client.create_resume("Resume")
            assert "Authentication failed" in str(exc_info.value)

    def test_raises_on_error(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=500, text="Server error")
            with pytest.raises(RuntimeError):
                client.create_resume("Resume")

    def test_raises_on_missing_id(self, client):
        with patch("requests.post") as mock_post:
            mock_post.return_value = Mock(status_code=200, json=lambda: {})
            with pytest.raises(RuntimeError) as exc_info:
                client.create_resume("Resume")
            assert "Failed to get resume ID" in str(exc_info.value)


class TestUpdateResume:
    def test_updates_resume_with_data(self, client):
        with patch("requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)
            result = client.update_resume("resume-id", {"basics": {"name": "John Doe"}})
            assert result is True
            call_args = mock_put.call_args
            assert call_args[1]["json"] == {"data": {"basics": {"name": "John Doe"}}}

    def test_raises_on_401(self, client):
        with patch("requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=401)
            with pytest.raises(RuntimeError) as exc_info:
                client.update_resume("id", {})
            assert "Authentication failed" in str(exc_info.value)

    def test_raises_on_404(self, client):
        with patch("requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=404)
            with pytest.raises(RuntimeError) as exc_info:
                client.update_resume("nonexistent", {})
            assert "not found" in str(exc_info.value)


class TestDeleteResume:
    def test_returns_true_on_success(self, client):
        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = Mock(status_code=200)
            result = client.delete_resume("resume-id")
            assert result is True

    def test_returns_true_on_404(self, client):
        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = Mock(status_code=404)
            result = client.delete_resume("nonexistent")
            assert result is True

    def test_returns_false_on_error(self, client):
        with patch("requests.delete") as mock_delete:
            mock_delete.return_value = Mock(status_code=500)
            result = client.delete_resume("resume-id")
            assert result is False

    def test_returns_false_on_request_exception(self, client):
        with patch("requests.delete") as mock_delete:
            mock_delete.side_effect = requests.RequestException("Error")
            result = client.delete_resume("resume-id")
            assert result is False


class TestGetResumeUrl:
    def test_returns_full_url(self, client):
        url = client.get_resume_url("abc123")
        assert url == "http://localhost:3000/builder/abc123"

    def test_uses_base_url_without_trailing_slash(self):
        client = ReactiveResumeClient("http://localhost:3000/", "key")
        url = client.get_resume_url("abc123")
        assert url == "http://localhost:3000/builder/abc123"

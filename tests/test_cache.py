"""Unit tests for CacheManager."""

import tempfile
from pathlib import Path

import pytest

from fast_app.services.cache import (
    CacheManager,
    generate_job_id,
    sanitize_path_component,
)


@pytest.fixture
def temp_output_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def cache_manager(temp_output_dir):
    return CacheManager(temp_output_dir)


class TestSanitizePathComponent:
    def test_removes_special_characters(self):
        assert sanitize_path_component("Company@Name!") == "CompanyName"
        assert sanitize_path_component("foo#bar$baz") == "foobarbaz"

    def test_replaces_spaces_and_hyphens(self):
        assert sanitize_path_component("Company Name") == "Company-Name"
        assert sanitize_path_component("company  name") == "company-name"
        assert sanitize_path_component("company - name") == "company-name"

    def test_truncates_long_names(self):
        long_name = "a" * 100
        result = sanitize_path_component(long_name)
        assert len(result) == 50
        assert result == "a" * 50

    def test_strips_trailing_hyphens(self):
        assert sanitize_path_component("company-") == "company"
        assert sanitize_path_component("company---") == "company"

    def test_returns_unknown_for_empty_string(self):
        assert sanitize_path_component("") == "unknown"
        assert sanitize_path_component("   ") == "unknown"

    def test_handles_unicode(self):
        result = sanitize_path_component("Café Française")
        assert "Caf" in result or result == "unknown"


class TestGenerateJobId:
    def test_generates_consistent_hash(self):
        url = "https://example.com/job/123"
        id1 = generate_job_id(url)
        id2 = generate_job_id(url)
        assert id1 == id2
        assert len(id1) == 12

    def test_different_urls_different_ids(self):
        url1 = "https://example.com/job/123"
        url2 = "https://example.com/job/456"
        assert generate_job_id(url1) != generate_job_id(url2)

    def test_is_alphanumeric(self):
        url = "https://example.com/job/123"
        job_id = generate_job_id(url)
        assert job_id.isalnum()


class TestCacheManagerInit:
    def test_sets_output_dir(self, temp_output_dir):
        cache = CacheManager(temp_output_dir)
        assert cache.output_dir == temp_output_dir


class TestGetJobDir:
    def test_creates_directory_path(self, cache_manager, temp_output_dir):
        job_dir = cache_manager.get_job_dir("Acme Corp", "Software Engineer", "abc123")
        expected = temp_output_dir / "Acme-Corp" / "Software-Engineer" / "abc123"
        assert job_dir == expected

    def test_creates_directory_when_create_true(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        assert job_dir.exists()
        assert job_dir.is_dir()

    def test_does_not_create_directory_when_create_false(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=False)
        assert not job_dir.exists()

    def test_sanitizes_company_and_title(self, cache_manager, temp_output_dir):
        job_dir = cache_manager.get_job_dir("Acme@Corp", "Software Engineer!", "abc")
        expected = temp_output_dir / "AcmeCorp" / "Software-Engineer" / "abc"
        assert job_dir == expected


class TestSaveAndLoadJob:
    def test_saves_and_loads_job_data(self, cache_manager, temp_output_dir):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        job_data = {"title": "Software Engineer", "company": "Acme"}

        cache_manager.save_job(job_dir, job_data)

        job_file = job_dir / "job.json"
        assert job_file.exists()

        loaded = cache_manager.get_cached_job(job_dir)
        assert loaded == job_data

    def test_returns_none_if_file_not_found(self, cache_manager):
        nonexistent_dir = cache_manager.output_dir / "nonexistent"
        result = cache_manager.get_cached_job(nonexistent_dir)
        assert result is None

    def test_returns_none_if_invalid_json(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        (job_dir / "job.json").write_text("invalid json")
        result = cache_manager.get_cached_job(job_dir)
        assert result is None


class TestSaveAndLoadQuestions:
    def test_saves_and_loads_questions(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        questions = ["What is your experience?", "Why this role?"]

        cache_manager.save_questions(job_dir, questions)

        loaded = cache_manager.get_cached_questions(job_dir)
        assert loaded == questions

    def test_returns_empty_list_if_none(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        result = cache_manager.get_cached_questions(job_dir)
        assert result is None


class TestSaveAndLoadAnswers:
    def test_saves_and_loads_answers(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        answers = ["5 years experience", "Interested in growth"]

        cache_manager.save_answers(job_dir, answers)

        loaded = cache_manager.get_cached_answers(job_dir)
        assert loaded == answers


class TestSaveAndLoadResume:
    def test_saves_and_loads_resume_data(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        resume_data = {"basics": {"name": "John Doe"}, "sections": {}}

        cache_manager.save_resume(job_dir, resume_data)

        loaded = cache_manager.get_cached_resume(job_dir)
        assert loaded == resume_data


class TestSaveAndLoadReactiveResume:
    def test_saves_and_loads_reactive_resume_metadata(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        metadata = {"resume_id": "abc-123", "title": "Engineer at Acme"}

        cache_manager.save_reactive_resume(job_dir, metadata)

        loaded = cache_manager.get_cached_reactive_resume(job_dir)
        assert loaded == metadata


class TestFindJobByHash:
    def test_finds_job_by_hash(self, cache_manager):
        cache_manager.save_job(
            cache_manager.get_job_dir("Acme", "Engineer", "abc123def456", create=True),
            {"title": "Software Engineer"},
        )

        found_dir = cache_manager.find_job_by_hash("abc123def456")
        assert found_dir is not None
        assert found_dir.name == "abc123def456"

    def test_returns_none_if_not_found(self, cache_manager):
        result = cache_manager.find_job_by_hash("nonexistent")
        assert result is None

    def test_returns_none_if_output_dir_does_not_exist(self, temp_output_dir):
        nonexistent = temp_output_dir / "nonexistent"
        cache = CacheManager(nonexistent)
        result = cache.find_job_by_hash("abc123")
        assert result is None

    def test_finds_nested_job(self, cache_manager):
        job_dir = cache_manager.get_job_dir(
            "Parent Company", "Senior Engineer", "xyz789", create=True
        )
        cache_manager.save_job(job_dir, {"title": "Senior Engineer"})

        found = cache_manager.find_job_by_hash("xyz789")
        assert found is not None
        assert found.name == "xyz789"


class TestHasCachedJob:
    def test_returns_path_if_cached(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "abc123", create=True)
        cache_manager.save_job(job_dir, {"title": "Engineer"})

        url = "https://example.com/job/123"
        result = cache_manager.has_cached_job(url)
        assert result is not None
        assert result.name == generate_job_id(url)

    def test_returns_none_if_not_cached(self, cache_manager):
        result = cache_manager.has_cached_job("https://example.com/job/999")
        assert result is None


class TestCoverLetter:
    def test_saves_and_loads_cover_letter(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        cover_letter = {"recipient": "Hiring Manager", "content": "Dear Hiring Manager..."}

        cache_manager.save_cover_letter(job_dir, cover_letter)

        loaded = cache_manager.get_cached_cover_letter(job_dir)
        assert loaded == cover_letter

    def test_saves_and_loads_reactive_cover_letter_metadata(self, cache_manager):
        job_dir = cache_manager.get_job_dir("Acme", "Engineer", "123", create=True)
        metadata = {"cover_letter_id": "cl-123", "title": "Cover Letter"}

        cache_manager.save_reactive_cover_letter(job_dir, metadata)

        loaded = cache_manager.get_cached_reactive_cover_letter(job_dir)
        assert loaded == metadata

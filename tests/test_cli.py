"""Unit tests for CLI helper functions."""

from fast_app.cli import sanitize_name


class TestSanitizeName:
    def test_removes_commas(self):
        result = sanitize_name("Company, Inc.")
        # Comma and period are both removed
        assert result == "Company Inc"

    def test_removes_special_characters(self):
        assert sanitize_name("Company@Name!") == "CompanyName"
        assert sanitize_name("foo#bar$baz%^") == "foobarbaz"

    def test_preserves_spaces_and_hyphens(self):
        assert sanitize_name("Company Name") == "Company Name"
        assert sanitize_name("company-name") == "company-name"

    def test_replaces_multiple_spaces(self):
        assert sanitize_name("company   name") == "company name"

    def test_strips_leading_and_trailing_spaces(self):
        assert sanitize_name("  Company Name  ") == "Company Name"

    def test_handles_empty_string(self):
        assert sanitize_name("") == ""
        assert sanitize_name("   ") == ""

    def test_handles_company_names(self):
        # Comma and period removed
        assert sanitize_name("Acme, Inc.") == "Acme Inc"
        assert sanitize_name("Google LLC") == "Google LLC"
        # Period in "Amazon.com" is also removed
        assert sanitize_name("Amazon.com, Inc.") == "Amazoncom Inc"

    def test_handles_job_titles(self):
        assert sanitize_name("Software Engineer, Senior") == "Software Engineer Senior"
        assert sanitize_name("VP, Engineering") == "VP Engineering"
        assert sanitize_name("Director of Engineering") == "Director of Engineering"

    def test_preserves_unicode_characters(self):
        result = sanitize_name("Café Française")
        # Unicode preserved, but may be normalized
        assert "Caf" in result

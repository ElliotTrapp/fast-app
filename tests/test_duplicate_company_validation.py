"""Tests for ResumeContent duplicate company validation."""

import pytest

from fast_app.models import (
    ExperienceItem,
    ExperienceSection,
    RoleItem,
    Sections,
)


class TestDuplicateCompanyValidation:
    """Test that duplicate company names in experience are detected and rejected."""

    def test_single_company_single_role_passes(self):
        """Single company with single role should pass validation."""
        item = ExperienceItem(
            company="NASA JPL",
            roles=[RoleItem(position="Engineer", description="<ul><li>Built things</li></ul>")],
        )
        sections = Sections(experience=ExperienceSection(items=[item]))
        assert sections.experience.items[0].company == "NASA JPL"

    def test_single_company_multiple_roles_passes(self):
        """Single company with multiple roles should pass validation."""
        item = ExperienceItem(
            company="NASA JPL",
            roles=[
                RoleItem(
                    position="Team Lead",
                    period="2020-2025",
                    description="<ul><li>Led team</li></ul>",
                ),
                RoleItem(
                    position="Engineer",
                    period="2018-2020",
                    description="<ul><li>Coded</li></ul>",
                ),
            ],
        )
        sections = Sections(experience=ExperienceSection(items=[item]))
        assert len(sections.experience.items[0].roles) == 2

    def test_different_companies_passes(self):
        """Different companies should pass validation."""
        items = [
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Engineer")]),
            ExperienceItem(company="Google", roles=[RoleItem(position="SWE")]),
            ExperienceItem(company="Apple", roles=[RoleItem(position="PM")]),
        ]
        sections = Sections(experience=ExperienceSection(items=items))
        assert len(sections.experience.items) == 3

    def test_duplicate_companies_rejected(self):
        """Duplicate company names should raise ValueError."""
        items = [
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Team Lead")]),
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Engineer")]),
        ]
        with pytest.raises(ValueError, match="DUPLICATE COMPANIES DETECTED"):
            Sections(experience=ExperienceSection(items=items))

    def test_duplicate_companies_case_insensitive(self):
        """Duplicate detection should be case-insensitive."""
        items = [
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Team Lead")]),
            ExperienceItem(company="nasa jpl", roles=[RoleItem(position="Engineer")]),
        ]
        with pytest.raises(ValueError, match="DUPLICATE COMPANIES DETECTED"):
            Sections(experience=ExperienceSection(items=items))

    def test_duplicate_companies_whitespace_normalized(self):
        """Duplicate detection should normalize whitespace."""
        items = [
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Team Lead")]),
            ExperienceItem(company="NASA  JPL", roles=[RoleItem(position="Engineer")]),
        ]
        sections = Sections(experience=ExperienceSection(items=items))
        assert len(sections.experience.items) == 2

    def test_empty_company_name_ignored(self):
        """Empty company names should not cause duplicate detection."""
        items = [
            ExperienceItem(company="", roles=[RoleItem(position="Engineer")]),
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="SWE")]),
        ]
        sections = Sections(experience=ExperienceSection(items=items))
        assert len(sections.experience.items) == 2

    def test_error_message_includes_guidance(self):
        """Error message should include guidance on using roles array."""
        items = [
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Team Lead")]),
            ExperienceItem(company="NASA JPL", roles=[RoleItem(position="Engineer")]),
        ]
        with pytest.raises(ValueError) as exc_info:
            Sections(experience=ExperienceSection(items=items))
        error_msg = str(exc_info.value)
        assert "'roles' array" in error_msg
        assert "unique 'company' field" in error_msg

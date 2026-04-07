"""Tests for prompt templates and schema validation."""

from fast_app.models import (
    Basics,
    CoverLetterData,
    EducationItem,
    ExperienceItem,
    QuestionData,
    ResumeData,
    Sections,
    SkillItem,
    Summary,
)
from fast_app.prompts.questions import get_questions_prompt
from fast_app.prompts.resume import get_resume_prompt
from fast_app.prompts.cover_letter import get_cover_letter_prompt


class TestGetResumePrompt:
    def test_includes_job_data(self):
        job_data = {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "location": "San Francisco, CA",
            "description": "Build great software",
            "skills": "Python, JavaScript",
        }
        profile_data = {"basics": {"name": "John Doe"}}

        prompt = get_resume_prompt(job_data, profile_data)

        assert "Software Engineer" in prompt
        assert "Acme Corp" in prompt
        assert "San Francisco, CA" in prompt
        assert "Build great software" in prompt
        assert "Python, JavaScript" in prompt

    def test_includes_profile_data(self):
        job_data = {"title": "Engineer"}
        profile_data = {
            "basics": {"name": "John Doe", "email": "john@example.com"},
            "work": [{"company": "Previous Corp"}],
        }

        prompt = get_resume_prompt(job_data, profile_data)

        assert "John Doe" in prompt
        assert "john@example.com" in prompt
        assert "Previous Corp" in prompt

    def test_includes_questions_and_answers(self):
        job_data = {"title": "Engineer"}
        profile_data = {"basics": {"name": "John Doe"}}
        questions = ["What is your experience?", "Why this role?"]
        answers = ["5 years of experience", "Interested in growth"]

        prompt = get_resume_prompt(job_data, profile_data, questions, answers)

        assert "Candidate's Additional Context" in prompt
        assert "What is your experience?" in prompt
        assert "5 years of experience" in prompt

    def test_handles_missing_questions(self):
        job_data = {"title": "Engineer"}
        profile_data = {"basics": {"name": "John Doe"}}

        prompt = get_resume_prompt(job_data, profile_data, questions=None, answers=None)

        assert "Candidate's Additional Context" not in prompt

    def test_filters_empty_answers(self):
        job_data = {"title": "Engineer"}
        profile_data = {"basics": {"name": "John Doe"}}
        questions = ["Q1", "Q2", "Q3"]
        answers = ["Answer 1", "", "Answer 3"]

        prompt = get_resume_prompt(job_data, profile_data, questions, answers)

        assert "Answer 1" in prompt
        assert "Answer 3" in prompt


class TestGetQuestionsPrompt:
    def test_includes_job_data(self):
        job_data = {
            "title": "Software Engineer",
            "company": "Acme Corp",
            "description": "Build software",
            "skills": "Python",
        }
        profile_data = {"basics": {"name": "John Doe"}}

        prompt = get_questions_prompt(job_data, profile_data)

        assert "Software Engineer" in prompt
        assert "Acme Corp" in prompt
        assert "Build software" in prompt

    def test_includes_profile(self):
        job_data = {"title": "Engineer"}
        profile_data = {
            "basics": {"name": "Jane Doe"},
            "work": [{"company": "Acme"}],
        }

        prompt = get_questions_prompt(job_data, profile_data)

        assert "Jane Doe" in prompt


class TestQuestionDataModel:
    def test_empty_questions(self):
        model = QuestionData()
        assert model.questions == []

    def test_with_questions(self):
        model = QuestionData(questions=["Q1?", "Q2?"])
        assert len(model.questions) == 2
        assert model.questions[0] == "Q1?"

    def model_json_schema(self):
        schema = QuestionData.model_json_schema()
        assert "properties" in schema
        assert "questions" in schema["properties"]


class TestResumeDataModel:
    def test_defaults(self):
        resume = ResumeData()
        assert resume.basics.name == ""
        assert resume.basics.headline == ""
        assert resume.summary.content == ""
        assert len(resume.sections.experience.items) == 0

    def test_populates_basics(self):
        resume = ResumeData(
            basics=Basics(name="John Doe", headline="Engineer", email="john@example.com")
        )
        assert resume.basics.name == "John Doe"
        assert resume.basics.headline == "Engineer"

    def test_populates_sections(self):
        from pydantic import BaseModel

        # Get the experience section type
        resume = ResumeData()
        experience_section = resume.sections.experience

        # Create an experience item
        experience_item = ExperienceItem(
            company="Acme",
            position="Engineer",
            location="SF",
            description="Built things",
        )
        experience_section.items.append(experience_item)

        resume = ResumeData(sections=resume.sections)
        assert len(resume.sections.experience.items) == 1
        assert resume.sections.experience.items[0].company == "Acme"

    def test_model_validate_json(self):
        json_data = """
        {
            "basics": {
                "name": "John Doe",
                "headline": "Engineer",
                "email": "john@example.com",
                "phone": "555-1234",
                "location": "San Francisco"
            },
            "summary": {
                "content": "Experienced engineer"
            },
            "sections": {}
        }
        """
        resume = ResumeData.model_validate_json(json_data)
        assert resume.basics.name == "John Doe"
        assert resume.basics.headline == "Engineer"
        assert resume.summary.content == "Experienced engineer"

    def test_model_json_schema(self):
        schema = ResumeData.model_json_schema()
        assert "properties" in schema
        assert "basics" in schema["properties"]
        assert "sections" in schema["properties"]


class TestBasicsModel:
    def test_defaults(self):
        basics = Basics()
        assert basics.name == ""
        assert basics.headline == ""
        assert basics.email == ""
        assert basics.phone == ""
        assert basics.location == ""

    def test_custom_fields(self):
        basics = Basics(
            name="Jane Doe",
            headline="Sr Engineer",
            email="jane@example.com",
            phone="555-0000",
            location="NYC",
        )
        assert basics.name == "Jane Doe"


class TestSummaryModel:
    def test_defaults(self):
        summary = Summary()
        assert summary.title == ""
        assert summary.content == ""
        assert summary.hidden is False


class TestExperienceItem:
    def test_defaults(self):
        item = ExperienceItem()
        assert item.company == ""
        assert item.position == ""
        assert item.hidden is False

    def test_with_data(self):
        item = ExperienceItem(
            company="Acme",
            position="Engineer",
            location="SF",
            description="Built things",
        )
        assert item.company == "Acme"
        assert item.roles == []


class TestSkillItem:
    def test_defaults(self):
        skill = SkillItem()
        assert skill.name == ""
        assert skill.level == 0
        assert skill.hidden is False


class TestEducationItem:
    def test_defaults(self):
        edu = EducationItem()
        assert edu.school == ""
        assert edu.degree == ""
        assert edu.hidden is False

    def test_with_data(self):
        edu = EducationItem(school="MIT", degree="BS Computer Science", location="Cambridge, MA")
        assert edu.school == "MIT"


class TestCoverLetterData:
    def test_defaults(self):
        cl = CoverLetterData()
        assert cl.recipient == ""
        assert cl.content == ""

    def test_with_data(self):
        cl = CoverLetterData(
            recipient="<p>Dear Hiring Manager,</p>",
            content="<p>Cover letter body...</p>",
        )
        assert cl.recipient == "<p>Dear Hiring Manager,</p>"
        assert "Cover letter body" in cl.content

    def test_model_json_schema(self):
        schema = CoverLetterData.model_json_schema()
        assert "recipient" in schema["properties"]
        assert "content" in schema["properties"]
        # These have defaults, so they're not required
        assert "recipient" in schema["properties"]
        assert "content" in schema["properties"]

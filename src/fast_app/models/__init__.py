"""Pydantic models matching Reactive Resume's ResumeData schema."""

import uuid
from typing import Any

from pydantic import BaseModel, Field


def generate_id() -> str:
    return str(uuid.uuid4())


class URL(BaseModel):
    url: str = ""
    label: str = ""


class Picture(BaseModel):
    hidden: bool = False
    url: str = ""
    size: int = 80
    rotation: int = 0
    aspectRatio: float = 1.0
    borderRadius: int = 0
    borderColor: str = "rgba(0, 0, 0, 0.5)"
    borderWidth: int = 0
    shadowColor: str = "rgba(0, 0, 0, 0.5)"
    shadowWidth: int = 0


class CustomField(BaseModel):
    id: str = Field(default_factory=generate_id)
    icon: str = ""
    text: str = ""
    link: str = ""


class Basics(BaseModel):
    name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    website: URL = Field(default_factory=URL)
    customFields: list[CustomField] = Field(default_factory=list)


class Summary(BaseModel):
    title: str = ""
    columns: int = 1
    hidden: bool = False
    content: str = ""


class RoleItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    position: str = ""
    period: str = ""
    description: str = ""


class ExperienceItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    company: str = ""
    position: str = ""
    location: str = ""
    period: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""
    roles: list[RoleItem] = Field(default_factory=list)


class EducationItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    school: str = ""
    degree: str = ""
    area: str = ""
    grade: str = ""
    location: str = ""
    period: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class SkillItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    icon: str = "star"
    name: str = ""
    proficiency: str = ""
    level: int = 0
    keywords: list[str] = Field(default_factory=list)


class LanguageItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    language: str = ""
    fluency: str = ""
    level: int = 0


class InterestItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    icon: str = "star"
    name: str = ""
    keywords: list[str] = Field(default_factory=list)


class ProfileItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    icon: str = "star"
    network: str = ""
    username: str = ""
    website: URL = Field(default_factory=URL)


class ProjectItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    name: str = ""
    period: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class AwardItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    title: str = ""
    awarder: str = ""
    date: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class CertificationItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    title: str = ""
    issuer: str = ""
    date: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class PublicationItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    title: str = ""
    publisher: str = ""
    date: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class VolunteerItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    organization: str = ""
    location: str = ""
    period: str = ""
    website: URL = Field(default_factory=URL)
    description: str = ""


class ReferenceItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    name: str = ""
    position: str = ""
    website: URL = Field(default_factory=URL)
    phone: str = ""
    description: str = ""


class ProfileSection(BaseModel):
    title: str = "Profiles"
    columns: int = 1
    hidden: bool = False
    items: list[ProfileItem] = Field(default_factory=list)


class ExperienceSection(BaseModel):
    title: str = "Experience"
    columns: int = 1
    hidden: bool = False
    items: list[ExperienceItem] = Field(default_factory=list)


class EducationSection(BaseModel):
    title: str = "Education"
    columns: int = 1
    hidden: bool = False
    items: list[EducationItem] = Field(default_factory=list)


class ProjectSection(BaseModel):
    title: str = "Projects"
    columns: int = 1
    hidden: bool = False
    items: list[ProjectItem] = Field(default_factory=list)


class SkillSection(BaseModel):
    title: str = "Skills"
    columns: int = 1
    hidden: bool = False
    items: list[SkillItem] = Field(default_factory=list)


class LanguageSection(BaseModel):
    title: str = "Languages"
    columns: int = 1
    hidden: bool = False
    items: list[LanguageItem] = Field(default_factory=list)


class InterestSection(BaseModel):
    title: str = "Interests"
    columns: int = 1
    hidden: bool = False
    items: list[InterestItem] = Field(default_factory=list)


class AwardSection(BaseModel):
    title: str = "Awards"
    columns: int = 1
    hidden: bool = False
    items: list[AwardItem] = Field(default_factory=list)


class CertificationSection(BaseModel):
    title: str = "Certifications"
    columns: int = 1
    hidden: bool = False
    items: list[CertificationItem] = Field(default_factory=list)


class PublicationSection(BaseModel):
    title: str = "Publications"
    columns: int = 1
    hidden: bool = False
    items: list[PublicationItem] = Field(default_factory=list)


class VolunteerSection(BaseModel):
    title: str = "Volunteer"
    columns: int = 1
    hidden: bool = False
    items: list[VolunteerItem] = Field(default_factory=list)


class ReferenceSection(BaseModel):
    title: str = "References"
    columns: int = 1
    hidden: bool = False
    items: list[ReferenceItem] = Field(default_factory=list)


class CoverLetterItem(BaseModel):
    id: str = Field(default_factory=generate_id)
    hidden: bool = False
    recipient: str = ""
    content: str = ""


class CoverLetterSection(BaseModel):
    title: str = "Cover Letter"
    columns: int = 1
    hidden: bool = False
    id: str = Field(default_factory=generate_id)
    type: str = "cover-letter"
    items: list[CoverLetterItem] = Field(default_factory=list)


class Sections(BaseModel):
    profiles: ProfileSection = Field(default_factory=ProfileSection)
    experience: ExperienceSection = Field(default_factory=ExperienceSection)
    education: EducationSection = Field(default_factory=EducationSection)
    projects: ProjectSection = Field(default_factory=ProjectSection)
    skills: SkillSection = Field(default_factory=SkillSection)
    languages: LanguageSection = Field(default_factory=LanguageSection)
    interests: InterestSection = Field(default_factory=InterestSection)
    awards: AwardSection = Field(default_factory=AwardSection)
    certifications: CertificationSection = Field(default_factory=CertificationSection)
    publications: PublicationSection = Field(default_factory=PublicationSection)
    volunteer: VolunteerSection = Field(default_factory=VolunteerSection)
    references: ReferenceSection = Field(default_factory=ReferenceSection)


class Colors(BaseModel):
    primary: str = "rgba(220, 38, 38, 1)"
    text: str = "rgba(0, 0, 0, 1)"
    background: str = "rgba(255, 255, 255, 1)"


class Level(BaseModel):
    icon: str = "star"
    type: str = "circle"


class Design(BaseModel):
    colors: Colors = Field(default_factory=Colors)
    level: Level = Field(default_factory=Level)


class Typography(BaseModel):
    fontFamily: str = "IBM Plex Serif"
    fontWeights: list[str] = Field(default_factory=lambda: ["400", "500"])
    fontSize: int = 10
    lineHeight: float = 1.5


class Page(BaseModel):
    gapX: int = 4
    gapY: int = 6
    marginX: int = 14
    marginY: int = 12
    format: str = "a4"
    locale: str = "en-US"
    hideIcons: bool = False


class PageLayout(BaseModel):
    fullWidth: bool = False
    main: list[str] = Field(
        default_factory=lambda: [
            "profiles",
            "summary",
            "education",
            "experience",
            "projects",
            "volunteer",
            "references",
        ]
    )
    sidebar: list[str] = Field(
        default_factory=lambda: [
            "skills",
            "certifications",
            "awards",
            "languages",
            "interests",
            "publications",
        ]
    )


class Layout(BaseModel):
    sidebarWidth: int = 35
    pages: list[PageLayout] = Field(default_factory=lambda: [PageLayout()])


class CSS(BaseModel):
    enabled: bool = False
    value: str = ""


class Metadata(BaseModel):
    template: str = "onyx"
    layout: Layout = Field(default_factory=Layout)
    css: CSS = Field(default_factory=CSS)
    page: Page = Field(default_factory=Page)
    design: Design = Field(default_factory=Design)
    typography: dict[str, Typography] = Field(
        default_factory=lambda: {
            "body": Typography(),
            "heading": Typography(fontWeights=["600"], fontSize=14),
        }
    )
    notes: str = ""


class QuestionContent(BaseModel):
    """Generated questions from LLM."""

    questions: list[str] = Field(default_factory=list)


class ResumeContent(BaseModel):
    """Generated resume content from LLM - only what we ask the LLM for."""

    summary: Summary = Field(default_factory=Summary)
    sections: Sections = Field(default_factory=Sections)


class ResumeData(BaseModel):
    """Full resume document ready for Reactive Resume."""

    picture: Picture = Field(default_factory=Picture)
    basics: Basics = Field(default_factory=Basics)
    summary: Summary = Field(default_factory=Summary)
    sections: Sections = Field(default_factory=Sections)
    customSections: list[Any] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)


class CoverLetterContent(BaseModel):
    """Generated cover letter content from LLM - only what we ask the LLM for."""

    recipient: str = ""
    content: str = ""


class CoverLetterData(BaseModel):
    """Full cover letter document ready for Reactive Resume."""

    picture: Picture = Field(default_factory=Picture)
    basics: Basics = Field(default_factory=Basics)
    summary: Summary = Field(default_factory=Summary)
    sections: Sections = Field(default_factory=Sections)
    customSections: list[Any] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)


class JobData(BaseModel):
    id: str = ""
    job_url: str = ""
    job_url_direct: str | None = None
    site: str = ""
    title: str = ""
    company: str = ""
    location: str | None = None
    description: str | None = None
    job_type: str | None = None
    date_posted: str | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None
    interval: str | None = None
    is_remote: bool | None = None
    job_level: str | None = None
    job_function: str | None = None
    skills: str | None = None
    company_industry: str | None = None
    company_url: str | None = None
    company_description: str | None = None
    company_num_employees: str | None = None


class ProfileData(BaseModel):
    basics: dict[str, Any]
    work: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[dict[str, Any]] = Field(default_factory=list)
    awards: list[dict[str, Any]] = Field(default_factory=list)
    certificates: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    publications: list[dict[str, Any]] = Field(default_factory=list)
    preferences: dict[str, Any] | None = None
    narrative: dict[str, Any] | None = None


# Optional submodules (require [auth] or [knowledge] deps):
#   from fast_app.models.db_models import User, UserProfile
#   from fast_app.models.knowledge import ExtractedFact, KnowledgeSearchResult

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin: str = ""
    website: str = ""
    github: str = ""


class ExperienceEntry(BaseModel):
    # Immutable fields (AI must not change these)
    company: str = ""
    title: str = ""
    dates: str = ""
    location: str = ""
    # Mutable fields (AI can adapt these)
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class EducationEntry(BaseModel):
    institution: str = ""
    degree: str = ""
    dates: str = ""
    details: str = ""


class ProjectEntry(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    url: str = ""


class CVData(BaseModel):
    contact: ContactInfo = Field(default_factory=ContactInfo)
    summary: str = ""
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    raw_markdown: str = ""
    detected_language: str = "en"


class ExperienceContextEntry(BaseModel):
    """Real per-company context sent to the AI for tech-swapping, never shown in the final CV."""
    real_technologies: list[str] = Field(default_factory=list)
    real_achievements: list[str] = Field(default_factory=list)


class BaseCVStore(BaseModel):
    """Editable base CV: the CV data plus the hidden real-context keyed by company name."""
    cv: CVData = Field(default_factory=CVData)
    experience_context: dict[str, ExperienceContextEntry] = Field(default_factory=dict)


class JobDescription(BaseModel):
    raw_text: str
    title: str = ""
    company: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    detected_language: str = "en"


class ATSScore(BaseModel):
    overall_score: float = 0.0
    required_score: float = 0.0
    preferred_score: float = 0.0
    general_score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class AdaptationResult(BaseModel):
    original_cv: CVData
    adapted_cv: CVData
    ats_score: ATSScore
    pdf_filename: str = ""
    tech_swaps: list[str] = Field(default_factory=list)
    job_analysis: dict = Field(default_factory=dict)

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


class SkillCategory(BaseModel):
    """A named group of skills (e.g. "Languages", "Frameworks") decided by the AI."""
    name: str = ""
    skills: list[str] = Field(default_factory=list)


class CVData(BaseModel):
    contact: ContactInfo = Field(default_factory=ContactInfo)
    headline: str = ""
    summary: str = ""
    experience: list[ExperienceEntry] = Field(default_factory=list)
    education: list[EducationEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    skill_categories: list[SkillCategory] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    raw_markdown: str = ""
    detected_language: str = "en"


class ExperienceContextEntry(BaseModel):
    """Verified per-company evidence sent to the AI, never shown verbatim in the final CV."""
    real_technologies: list[str] = Field(default_factory=list)
    real_achievements: list[str] = Field(default_factory=list)


class BaseCVStore(BaseModel):
    """Editable base CV: the CV data plus the hidden real-context keyed by company name."""
    profile_id: str = "developer"
    display_name: str = "Developer"
    profile_type: str = "developer"
    cv: CVData = Field(default_factory=CVData)
    experience_context: dict[str, ExperienceContextEntry] = Field(default_factory=dict)


class ProfileDefinition(BaseModel):
    id: str
    display_name: str
    description: str = ""
    profile_type: str = "developer"
    default_template: str = "modern"
    content_language: str = "en"
    one_page_required: bool = False
    max_pages: int | None = None


class JobOpportunity(BaseModel):
    """A manually verified job snapshot that can be loaded into the generator."""
    id: str
    profile_id: str
    title: str
    company: str
    location: str = ""
    source_name: str = "LinkedIn"
    source_url: str
    checked_at: str
    status: str = "active"
    detected_language: str = "en"
    fit_note: str = ""
    job_description: str


class ClaimReview(BaseModel):
    status: str = "passed"
    direct_bpo_experience_claimed: bool = False
    unsupported_claims: list[str] = Field(default_factory=list)
    protected_fields_preserved: bool = True
    transferable_strengths: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
    original_ats_score: ATSScore = Field(default_factory=ATSScore)
    pdf_filename: str = ""
    tech_swaps: list[str] = Field(default_factory=list)
    job_analysis: dict = Field(default_factory=dict)
    profile_id: str = "developer"
    claim_review: ClaimReview = Field(default_factory=ClaimReview)

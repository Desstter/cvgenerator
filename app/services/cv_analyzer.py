import re
import json
import logging
from app.models.schemas import (
    CVData, ContactInfo, ExperienceEntry, EducationEntry, ProjectEntry,
)

logger = logging.getLogger(__name__)

# Section header patterns for EN and ES
SECTION_PATTERNS = {
    "summary": re.compile(
        r"^#+\s*(summary|about\s*me|profile|professional\s*summary|resumen|sobre\s*m[ií]|perfil)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "experience": re.compile(
        r"^#+\s*(experience|work\s*experience|professional\s*experience|experiencia|experiencia\s*laboral|experiencia\s*profesional)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "education": re.compile(
        r"^#+\s*(education|academic|educaci[oó]n|formaci[oó]n|formaci[oó]n\s*acad[eé]mica)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "skills": re.compile(
        r"^#+\s*(skills|technical\s*skills|technologies|habilidades|competencias|tecnolog[ií]as)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "projects": re.compile(
        r"^#+\s*(projects|personal\s*projects|proyectos)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certifications": re.compile(
        r"^#+\s*(certifications|certificates|certificaciones|certificados)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "languages": re.compile(
        r"^#+\s*(languages|idiomas)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}

# Common Spanish words for language detection
_ES_WORDS = {
    "experiencia", "laboral", "educación", "formación", "habilidades",
    "proyectos", "sobre", "idiomas", "certificaciones", "profesional",
    "empresa", "universidad", "desarrollo", "ingeniero", "programador",
}


def detect_language(text: str) -> str:
    lower = text.lower()
    es_count = sum(1 for w in _ES_WORDS if w in lower)
    return "es" if es_count >= 3 else "en"


def _split_sections(markdown: str) -> dict[str, str]:
    """Split markdown into named sections based on heading patterns."""
    heading_re = re.compile(r"^(#+\s*.+)$", re.MULTILINE)
    headings = list(heading_re.finditer(markdown))

    sections: dict[str, str] = {}
    for i, match in enumerate(headings):
        heading_text = match.group(1)
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(markdown)
        content = markdown[start:end].strip()

        for section_name, pattern in SECTION_PATTERNS.items():
            if pattern.match(heading_text):
                sections[section_name] = content
                break

    # Everything before the first heading is potential contact/header info
    if headings:
        sections["header"] = markdown[:headings[0].start()].strip()

    return sections


def _parse_contact(header: str) -> ContactInfo:
    contact = ContactInfo()
    lines = [l.strip() for l in header.split("\n") if l.strip()]
    if lines:
        # First non-empty line is usually the name
        name_line = lines[0].strip("#").strip("*").strip()
        if name_line and "@" not in name_line:
            contact.name = name_line

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", header)
    if email_match:
        contact.email = email_match.group(0)

    phone_match = re.search(r"[\+]?[\d\s\-().]{7,15}", header)
    if phone_match:
        contact.phone = phone_match.group(0).strip()

    linkedin_match = re.search(r"linkedin\.com/in/[\w-]+", header, re.IGNORECASE)
    if linkedin_match:
        contact.linkedin = linkedin_match.group(0)

    return contact


def _parse_experience(text: str) -> list[ExperienceEntry]:
    entries = []
    # Split by bold patterns or sub-headings that typically mark new roles
    # Common patterns: **Company** or ### Title or **Title** at Company
    blocks = re.split(r"\n(?=\*\*|###)", text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        entry = ExperienceEntry()

        lines = block.split("\n")
        first_line = lines[0].strip("#").strip("*").strip()

        # Try to extract dates from the block
        date_match = re.search(
            r"(\w+\.?\s*\d{4}\s*[-–—]\s*(?:\w+\.?\s*\d{4}|present|actual|presente|current)|\d{4}\s*[-–—]\s*(?:\d{4}|present|actual|presente|current))",
            block, re.IGNORECASE,
        )
        if date_match:
            entry.dates = date_match.group(0).strip()

        # First line is usually title or company
        entry.title = first_line
        if len(lines) > 1:
            second = lines[1].strip("*").strip("_").strip()
            # If second line looks like a company name (no bullet)
            if second and not second.startswith(("-", "•", "*")):
                entry.company = second

        # Collect description bullets
        desc_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("-", "•", "*")) and not stripped.startswith("**"):
                desc_lines.append(stripped)
        entry.description = "\n".join(desc_lines)

        # Extract technologies from description
        tech_match = re.search(
            r"(?:technologies|tech(?:nical)?\s*stack|tools|tecnolog[ií]as)[:\s]*(.+)",
            block, re.IGNORECASE,
        )
        if tech_match:
            techs = re.split(r"[,·•|]", tech_match.group(1))
            entry.technologies = [t.strip().strip("*").strip() for t in techs if t.strip()]

        if entry.title or entry.description:
            entries.append(entry)

    return entries


def _parse_education(text: str) -> list[EducationEntry]:
    entries = []
    blocks = re.split(r"\n(?=\*\*|###)", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        entry = EducationEntry()
        lines = block.split("\n")
        entry.degree = lines[0].strip("#").strip("*").strip()
        if len(lines) > 1:
            entry.institution = lines[1].strip("*").strip("_").strip()
        date_match = re.search(r"\d{4}\s*[-–—]\s*(?:\d{4}|present|actual)", block, re.IGNORECASE)
        if date_match:
            entry.dates = date_match.group(0)
        details = [l.strip() for l in lines[2:] if l.strip().startswith(("-", "•"))]
        entry.details = "\n".join(details)
        if entry.degree:
            entries.append(entry)
    return entries


def _parse_skills(text: str) -> list[str]:
    skills = []
    for line in text.split("\n"):
        line = line.strip().lstrip("-•* ")
        if not line:
            continue
        # Handle "Category: skill1, skill2" format
        if ":" in line:
            _, _, after = line.partition(":")
            parts = re.split(r"[,·•|]", after)
        else:
            parts = re.split(r"[,·•|]", line)
        for s in parts:
            s = s.strip().strip("*").strip("`").strip()
            if s and len(s) < 60:
                skills.append(s)
    return skills


def _parse_list(text: str) -> list[str]:
    items = []
    for line in text.split("\n"):
        line = line.strip().lstrip("-•* ")
        if line:
            items.append(line.strip("*").strip())
    return items


def _parse_projects(text: str) -> list[ProjectEntry]:
    entries = []
    blocks = re.split(r"\n(?=\*\*|###)", text)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        entry = ProjectEntry()
        lines = block.split("\n")
        entry.name = lines[0].strip("#").strip("*").strip()
        desc_lines = [l.strip() for l in lines[1:] if l.strip()]
        entry.description = "\n".join(desc_lines)
        url_match = re.search(r"https?://\S+", block)
        if url_match:
            entry.url = url_match.group(0)
        if entry.name:
            entries.append(entry)
    return entries


def analyze_cv_rule_based(markdown: str) -> CVData:
    """Parse CV markdown into structured CVData using regex rules."""
    sections = _split_sections(markdown)
    lang = detect_language(markdown)

    cv = CVData(
        detected_language=lang,
        raw_markdown=markdown,
    )

    if "header" in sections:
        cv.contact = _parse_contact(sections["header"])
    if "summary" in sections:
        cv.summary = sections["summary"]
    if "experience" in sections:
        cv.experience = _parse_experience(sections["experience"])
    if "education" in sections:
        cv.education = _parse_education(sections["education"])
    if "skills" in sections:
        cv.skills = _parse_skills(sections["skills"])
    if "projects" in sections:
        cv.projects = _parse_projects(sections["projects"])
    if "certifications" in sections:
        cv.certifications = _parse_list(sections["certifications"])
    if "languages" in sections:
        cv.languages = _parse_list(sections["languages"])

    return cv


def is_parse_sufficient(cv: CVData) -> bool:
    """Check if rule-based parsing captured enough structure."""
    has_experience = len(cv.experience) > 0
    has_skills = len(cv.skills) > 0
    has_contact = bool(cv.contact.name)
    return has_experience and has_skills and has_contact


def build_ai_parse_prompt(markdown: str) -> str:
    """Build a prompt for AI to parse the CV into structured JSON."""
    return f"""Parse the following CV markdown into a structured JSON object.
Return ONLY valid JSON matching this schema:
{{
  "contact": {{"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "website": ""}},
  "summary": "single paragraph string",
  "experience": [
    {{"company": "", "title": "", "dates": "", "location": "", "description": "string with bullet points separated by newlines", "technologies": ["tech1", "tech2"]}}
  ],
  "education": [
    {{"institution": "", "degree": "", "dates": "", "details": "string describing education details"}}
  ],
  "projects": [
    {{"name": "", "description": "string describing the project", "technologies": ["tech1", "tech2"], "url": ""}}
  ],
  "skills": ["skill1", "skill2"],
  "certifications": ["cert1", "cert2"],
  "languages": ["lang1", "lang2"]
}}

IMPORTANT: description, details, and summary fields must be STRINGS, not arrays.

CV Markdown:
{markdown}"""


def _clean_none_values(obj):
    """Recursively convert None values to empty strings or empty lists."""
    if isinstance(obj, dict):
        return {k: _clean_none_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_none_values(item) for item in obj]
    elif obj is None:
        return ""
    return obj


def _normalize_string_fields(obj, string_fields):
    """Convert list values to strings for specified fields (e.g., description)."""
    if not isinstance(obj, dict):
        return obj

    normalized = obj.copy()
    for field in string_fields:
        if field in normalized and isinstance(normalized[field], list):
            # Join list items with newlines, adding bullet points
            normalized[field] = "\n".join(f"• {item}" for item in normalized[field] if item)
    return normalized


def parse_ai_response_to_cv(json_str: str, markdown: str) -> CVData:
    """Parse AI JSON response into CVData."""
    # Extract JSON from potential markdown code blocks
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", json_str, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)

    data = json.loads(json_str)
    data = _clean_none_values(data)

    cv = CVData(
        raw_markdown=markdown,
        detected_language=detect_language(markdown),
    )
    if "contact" in data and data["contact"]:
        cv.contact = ContactInfo(**data["contact"])
    cv.summary = data.get("summary", "")

    # Normalize experience entries (description might be list or string)
    experience_data = data.get("experience", [])
    cv.experience = [
        ExperienceEntry(**_normalize_string_fields(e, ["description"]))
        for e in experience_data
    ]

    # Normalize education entries (details might be list or string)
    education_data = data.get("education", [])
    cv.education = [
        EducationEntry(**_normalize_string_fields(e, ["details"]))
        for e in education_data
    ]

    # Normalize project entries (description might be list or string)
    project_data = data.get("projects", [])
    cv.projects = [
        ProjectEntry(**_normalize_string_fields(p, ["description"]))
        for p in project_data
    ]

    cv.skills = data.get("skills", [])
    cv.certifications = data.get("certifications", [])
    cv.languages = data.get("languages", [])
    return cv


def validate_cv_data(cv: CVData) -> list[str]:
    """Validate parsed CV and return list of warnings."""
    warnings = []

    # Validate email
    if cv.contact.email:
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, cv.contact.email):
            warnings.append(f"Invalid email format: {cv.contact.email}")

    # Validate experience entries
    for i, exp in enumerate(cv.experience):
        if not exp.company:
            warnings.append(f"Experience entry {i+1}: Missing company name")
        if not exp.title:
            warnings.append(f"Experience entry {i+1}: Missing job title")
        if not exp.dates:
            warnings.append(f"Experience entry {i+1} ({exp.company or 'Unknown'}): Missing dates")
        # Check if dates make sense
        elif "-" in exp.dates:
            parts = exp.dates.split("-", 1)
            if len(parts) == 2:
                start, end = parts
                end = end.strip().lower()
                if end not in ["present", "actual", "presente", "current"] and not any(c.isdigit() for c in end):
                    warnings.append(f"Experience entry {i+1} ({exp.company or 'Unknown'}): Unclear end date '{end}'")

    # Validate education
    for i, edu in enumerate(cv.education):
        if not edu.institution:
            warnings.append(f"Education entry {i+1}: Missing institution")
        if not edu.degree:
            warnings.append(f"Education entry {i+1}: Missing degree")

    # Log warnings if any
    if warnings:
        logger.warning(f"CV validation found {len(warnings)} issue(s):")
        for warning in warnings:
            logger.warning(f"  - {warning}")

    return warnings

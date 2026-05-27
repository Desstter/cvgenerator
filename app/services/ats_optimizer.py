from difflib import SequenceMatcher
from app.models.schemas import CVData, JobDescription, ATSScore

# Synonym mapping for common technical terms
SYNONYM_MAP = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node.js",
    "node": "node.js",
    "k8s": "kubernetes",
    "ci/cd": "continuous integration",
    "cicd": "continuous integration",
    "devops": "development operations",
    "javascript": "js",
    "typescript": "ts",
    "python3": "python",
    "py": "python",
    "postgresql": "postgres",
    "nosql": "non-relational database",
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _normalize_with_synonyms(text: str) -> set[str]:
    """Normalize text and expand with synonyms."""
    normalized = _normalize(text)
    variants = {normalized}

    # Add synonyms
    for short, full in SYNONYM_MAP.items():
        if short in normalized:
            variants.add(normalized.replace(short, full))
        if full in normalized:
            variants.add(normalized.replace(full, short))

    return variants


def _fuzzy_match(keyword: str, text: str, threshold: float = 0.85) -> bool:
    """Check if keyword matches text approximately."""
    kw_norm = _normalize(keyword)

    # Exact match first
    if kw_norm in text:
        return True

    # Check synonyms
    for variant in _normalize_with_synonyms(keyword):
        if variant in text:
            return True

    # Fuzzy match for typos/variations
    words = text.split()
    for word in words:
        if len(word) > 3 and len(kw_norm) > 3:  # Only fuzzy match for words > 3 chars
            if SequenceMatcher(None, kw_norm, word).ratio() > threshold:
                return True

    return False


def _extract_cv_text(cv: CVData) -> str:
    """Combine all CV text into a single searchable string."""
    parts = [
        cv.summary,
        " ".join(cv.skills),
        " ".join(cv.certifications),
    ]
    for exp in cv.experience:
        parts.append(exp.description)
        parts.extend(exp.technologies)
    for proj in cv.projects:
        parts.append(proj.description)
        parts.extend(proj.technologies)
    return _normalize(" ".join(parts))


def analyze_keyword_match(cv: CVData, job: JobDescription) -> ATSScore:
    """Score how well the CV matches the job description keywords using weighted fuzzy matching."""
    cv_text = _extract_cv_text(cv)

    # Separate keywords by importance
    required = list(dict.fromkeys(job.required_skills))
    preferred = list(dict.fromkeys(job.preferred_skills))
    general = list(dict.fromkeys(job.keywords))

    # Match each category
    matched_req = [kw for kw in required if _fuzzy_match(kw, cv_text)]
    matched_pref = [kw for kw in preferred if _fuzzy_match(kw, cv_text)]
    matched_gen = [kw for kw in general if _fuzzy_match(kw, cv_text)]

    missing_req = [kw for kw in required if kw not in matched_req]
    missing_pref = [kw for kw in preferred if kw not in matched_pref]
    missing_gen = [kw for kw in general if kw not in matched_gen]

    # Weighted scoring: required=3x, preferred=2x, general=1x
    total_weight = len(required) * 3 + len(preferred) * 2 + len(general) * 1
    matched_weight = len(matched_req) * 3 + len(matched_pref) * 2 + len(matched_gen) * 1

    score = (matched_weight / total_weight * 100) if total_weight > 0 else 0

    # Combined lists for display (prioritize critical missing)
    matched = matched_req + matched_pref + matched_gen
    missing = missing_req + missing_pref + missing_gen

    # Generate context-aware suggestions
    suggestions = []
    if missing_req:
        suggestions.append(f"CRITICAL: Add required skills: {', '.join(missing_req[:3])}")
    if missing_pref:
        suggestions.append(f"Recommended: Include preferred skills: {', '.join(missing_pref[:3])}")
    if missing_gen and not missing_req and not missing_pref:
        suggestions.append(f"Consider adding: {', '.join(missing_gen[:3])}")

    if not suggestions:
        suggestions.append("Excellent match! Your CV covers all key requirements.")
    elif score >= 80:
        suggestions.append("Strong match! Your CV is well-aligned with this role.")
    elif score < 50:
        suggestions.append("Focus on adding the required skills listed above to improve your match.")

    return ATSScore(
        overall_score=round(score, 1),
        required_score=round(len(matched_req) / len(required) * 100 if required else 0, 1),
        preferred_score=round(len(matched_pref) / len(preferred) * 100 if preferred else 0, 1),
        general_score=round(len(matched_gen) / len(general) * 100 if general else 0, 1),
        matched_keywords=list(dict.fromkeys(matched_req + matched_pref + matched_gen)),
        missing_keywords=list(dict.fromkeys(missing_req + missing_pref + missing_gen)),
        suggestions=suggestions,
    )


def reorder_skills(skills: list[str], job_keywords: list[str]) -> list[str]:
    """Put matching skills first, then the rest."""
    kw_lower = {_normalize(k) for k in job_keywords}
    matching = []
    non_matching = []
    for skill in skills:
        if _normalize(skill) in kw_lower:
            matching.append(skill)
        else:
            non_matching.append(skill)
    return matching + non_matching

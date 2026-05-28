from difflib import SequenceMatcher
from app.models.schemas import CVData, JobDescription, ATSScore

# Synonym mapping for common technical terms.
# Direction is "short → long form": "ml" expands to "machine learning".
# The matcher checks both directions so order does not matter for symmetry.
SYNONYM_MAP = {
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "reactjs": "react",
    "react.js": "react",
    "nodejs": "node.js",
    "k8s": "kubernetes",
    "ci/cd": "continuous integration",
    "cicd": "continuous integration",
    "devops": "development operations",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "python3": "python",
    "postgresql": "postgres",
    "nosql": "non-relational database",
}


def _normalize(text: str) -> str:
    return text.lower().strip()


def _expand_with_synonyms(text: str, extra: dict[str, list[str]] | None = None) -> set[str]:
    """Return all synonym variants for a normalized term, including LLM-provided ones."""
    normalized = _normalize(text)
    variants: set[str] = {normalized}

    for short, full in SYNONYM_MAP.items():
        if short == normalized:
            variants.add(full)
        if full == normalized:
            variants.add(short)
        # word-substitution variants (for multi-word inputs like "ml engineer")
        if f" {short} " in f" {normalized} ":
            variants.add(normalized.replace(short, full))
        if f" {full} " in f" {normalized} ":
            variants.add(normalized.replace(full, short))

    if extra:
        # extra is a dict mapping canonical term -> list of equivalents
        for canonical, equivalents in extra.items():
            can_norm = _normalize(canonical)
            eq_norms = [_normalize(e) for e in equivalents]
            group = {can_norm, *eq_norms}
            if normalized in group:
                variants.update(group)

    return variants


def _fuzzy_match(
    keyword: str,
    text: str,
    extra_synonyms: dict[str, list[str]] | None = None,
    threshold: float = 0.85,
) -> bool:
    """Check if keyword matches text approximately (exact / synonym / fuzzy word)."""
    kw_norm = _normalize(keyword)

    if kw_norm in text:
        return True

    for variant in _expand_with_synonyms(keyword, extra_synonyms):
        if variant and variant in text:
            return True

    words = text.split()
    for word in words:
        if len(word) > 3 and len(kw_norm) > 3:
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


def analyze_keyword_match(
    cv: CVData,
    job: JobDescription,
    extra_synonyms: dict[str, list[str]] | None = None,
) -> ATSScore:
    """Score how well the CV matches the job description keywords using weighted fuzzy matching."""
    cv_text = _extract_cv_text(cv)

    required = list(dict.fromkeys(job.required_skills))
    preferred = list(dict.fromkeys(job.preferred_skills))
    general = list(dict.fromkeys(job.keywords))

    matched_req = [kw for kw in required if _fuzzy_match(kw, cv_text, extra_synonyms)]
    matched_pref = [kw for kw in preferred if _fuzzy_match(kw, cv_text, extra_synonyms)]
    matched_gen = [kw for kw in general if _fuzzy_match(kw, cv_text, extra_synonyms)]

    missing_req = [kw for kw in required if kw not in matched_req]
    missing_pref = [kw for kw in preferred if kw not in matched_pref]
    missing_gen = [kw for kw in general if kw not in matched_gen]

    total_weight = len(required) * 3 + len(preferred) * 2 + len(general) * 1
    matched_weight = len(matched_req) * 3 + len(matched_pref) * 2 + len(matched_gen) * 1
    score = (matched_weight / total_weight * 100) if total_weight > 0 else 0

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


def reorder_skills(
    skills: list[str],
    job_keywords: list[str],
    extra_synonyms: dict[str, list[str]] | None = None,
) -> list[str]:
    """Put skills that match any job keyword (via the same fuzzy/synonym logic as scoring) first."""
    matching: list[str] = []
    non_matching: list[str] = []
    for skill in skills:
        skill_norm = _normalize(skill)
        if any(_fuzzy_match(kw, skill_norm, extra_synonyms) for kw in job_keywords):
            matching.append(skill)
        else:
            non_matching.append(skill)
    return matching + non_matching

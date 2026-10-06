import re
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

BPO_EQUIVALENCES = {
    "customer service": ["customer support"],
    "communication skills": ["communication"],
    "problem solving": ["problem resolution"],
    "teamwork": ["team collaboration"],
    "english": ["english (upper-intermediate, b2+)", "english"],
}


def _merge_profile_synonyms(
    extra: dict[str, list[str]] | None,
    profile_type: str,
) -> dict[str, list[str]] | None:
    if profile_type != "bpo":
        return extra
    merged = {key: list(values) for key, values in BPO_EQUIVALENCES.items()}
    for key, values in (extra or {}).items():
        merged.setdefault(key, []).extend(value for value in values if value not in merged.get(key, []))
    return merged


def _normalize(text: str) -> str:
    return text.lower().strip()


def _expand_with_synonyms(text: str, extra: dict[str, list[str]] | None = None) -> set[str]:
    """Return synonym variants, including caller-owned curated equivalences."""
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
    """Match full terms only. Partial words and typo guesses inflate coverage."""
    for variant in _expand_with_synonyms(keyword, extra_synonyms):
        if variant and re.search(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", text):
            return True
    return False


def _extract_cv_text(cv: CVData) -> str:
    """Combine all CV text into a single searchable string."""
    parts = [
        cv.headline,
        cv.summary,
        " ".join(cv.skills),
        " ".join(cv.certifications),
        " ".join(cv.languages),
    ]
    for exp in cv.experience:
        parts.append(exp.description)
        parts.extend(exp.technologies)
    for proj in cv.projects:
        parts.append(proj.description)
        parts.extend(proj.technologies)
    return _normalize(" ".join(parts))


def _cv_evidence_pieces(cv: CVData) -> list[str]:
    pieces = [cv.headline, cv.summary, *cv.skills, *cv.certifications, *cv.languages]
    for exp in cv.experience:
        pieces.extend(exp.description.splitlines())
        pieces.extend(exp.technologies)
    for project in cv.projects:
        pieces.extend(project.description.splitlines())
        pieces.extend(project.technologies)
    return [piece.strip() for piece in pieces if piece.strip()]


def _unique_terms(terms: list[str], seen: set[str]) -> list[str]:
    output = []
    for term in terms:
        normalized = _normalize(term)
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(term)
    return output


def analyze_keyword_match(
    cv: CVData,
    job: JobDescription,
    extra_synonyms: dict[str, list[str]] | None = None,
    profile_type: str = "developer",
) -> ATSScore:
    """A local keyword-coverage estimate, not an external ATS prediction."""
    pieces = _cv_evidence_pieces(cv)
    extra_synonyms = _merge_profile_synonyms(extra_synonyms, profile_type)

    seen: set[str] = set()
    required = _unique_terms(job.required_skills, seen)
    preferred = _unique_terms(job.preferred_skills, seen)
    general = _unique_terms(job.keywords, seen)

    evidence = {
        term: next((piece for piece in pieces if _fuzzy_match(term, _normalize(piece), extra_synonyms)), "")
        for term in required + preferred + general
    }

    matched_req = [kw for kw in required if evidence[kw]]
    matched_pref = [kw for kw in preferred if evidence[kw]]
    matched_gen = [kw for kw in general if evidence[kw]]

    missing_req = [kw for kw in required if kw not in matched_req]
    missing_pref = [kw for kw in preferred if kw not in matched_pref]
    missing_gen = [kw for kw in general if kw not in matched_gen]

    total_weight = len(required) * 3 + len(preferred) * 2 + len(general) * 1
    matched_weight = len(matched_req) * 3 + len(matched_pref) * 2 + len(matched_gen) * 1
    score = (matched_weight / total_weight * 100) if total_weight > 0 else 0

    suggestions = []
    if profile_type == "bpo":
        if missing_req:
            suggestions.append(
                "Missing required terms: " + ", ".join(missing_req[:3])
                + ". Add them only if you can support them with a real example."
            )
        if missing_pref:
            suggestions.append(
                "Preferred terms not evidenced: " + ", ".join(missing_pref[:3])
                + ". Do not claim tools or duties you have not performed."
            )
        if missing_gen and not missing_req and not missing_pref:
            suggestions.append(
                "Prepare interview examples for: " + ", ".join(missing_gen[:3])
                + ", without adding unsupported experience to the CV."
            )
    else:
        if missing_req:
            suggestions.append(
                "Required skills not evidenced: " + ", ".join(missing_req[:3])
                + ". Add them only after you have real, interview-defensible experience."
            )
        if missing_pref:
            suggestions.append(
                "Preferred skills not evidenced: " + ", ".join(missing_pref[:3])
                + ". Treat these as a learning plan, not resume claims."
            )
        if missing_gen and not missing_req and not missing_pref:
            suggestions.append(
                "Prepare truthful examples for: " + ", ".join(missing_gen[:3])
                + "."
            )

    if not suggestions:
        suggestions.append("All extracted terms appear in the CV; review their relevance and evidence.")
    elif score < 50 and profile_type != "bpo":
        suggestions.append("Use the missing requirements to decide whether the role is a realistic fit.")
    elif score < 50:
        suggestions.append("A lower honest score is safer than an interview claim you cannot defend.")

    return ATSScore(
        overall_score=round(score, 1),
        required_score=round(len(matched_req) / len(required) * 100 if required else 0, 1),
        preferred_score=round(len(matched_pref) / len(preferred) * 100 if preferred else 0, 1),
        general_score=round(len(matched_gen) / len(general) * 100 if general else 0, 1),
        matched_keywords=list(dict.fromkeys(matched_req + matched_pref + matched_gen)),
        missing_keywords=list(dict.fromkeys(missing_req + missing_pref + missing_gen)),
        matched_evidence={kw: evidence[kw][:240] for kw in matched_req + matched_pref + matched_gen},
        suggestions=suggestions,
    )


def reorder_skills(
    skills: list[str],
    job_keywords: list[str],
    extra_synonyms: dict[str, list[str]] | None = None,
    profile_type: str = "developer",
) -> list[str]:
    """Put skills that match any job keyword (via the same fuzzy/synonym logic as scoring) first."""
    extra_synonyms = _merge_profile_synonyms(extra_synonyms, profile_type)
    matching: list[str] = []
    non_matching: list[str] = []
    for skill in skills:
        skill_norm = _normalize(skill)
        if any(_fuzzy_match(kw, skill_norm, extra_synonyms) for kw in job_keywords):
            matching.append(skill)
        else:
            non_matching.append(skill)
    return matching + non_matching

"""Deterministic truth guard applied after every AI adaptation.

The model may rewrite presentation, but code owns factual identity, titles,
skill inventory, technology lists, education and language proficiency.
"""

import re

from app.models.schemas import CVData, ClaimReview

UNSUPPORTED_TERMS = (
    "salesforce", "zendesk", "hubspot", "freshdesk", "genesys", "five9",
    "nice cxone", "inbound calls", "outbound calls", "cold calling",
    "upselling", "cross-selling", "collections", "retention calls",
    "billing support", "refund processing", "cash handling",
)

UNSUPPORTED_METRICS = (
    "csat", "customer satisfaction score", "aht", "average handling time",
    "first call resolution", "fcr", "calls per day", "tickets per day",
)

DIRECT_EXPERIENCE_PATTERNS = (
    re.compile(r"\b\d+\+?\s+years?\s+(?:of\s+)?(?:direct\s+)?(?:experience\s+)?(?:in|as|providing)?\s*(?:customer service|call[ -]?center|bpo|phone support)", re.I),
    re.compile(r"\bexperienced\s+(?:customer service|call[ -]?center|bpo)\s+(?:agent|representative|professional)", re.I),
    re.compile(r"\bworked\s+(?:in|at)\s+(?:a\s+)?(?:call[ -]?center|bpo|contact center)", re.I),
)

TRANSFERABLE_SIGNALS = {
    "Client solution delivery": ("client", "business user"),
    "Technical troubleshooting": ("troubleshoot", "investigat", "diagnos", "problem resolution"),
    "Team coordination": ("coordinat", "collaborat", "team"),
    "Issue documentation": ("document", "written communication"),
    "Sensitive-data awareness": ("sensitive", "privacy", "financial information"),
    "Remote-work experience": ("remote",),
}

KNOWN_TECH_TERMS = (
    "python", "django", "flask", "fastapi", "pytest", "javascript", "typescript",
    "react", "react native", "vue", "angular", "next.js", "node.js", "express",
    "nestjs", "java", "spring boot", ".net", "c#", "php", "laravel", "wordpress",
    "postgresql", "mysql", "sql server", "mongodb", "redis", "graphql", "rest api",
    "aws", "azure", "gcp", "oracle cloud", "docker", "kubernetes", "terraform",
    "jenkins", "github actions", "gitlab ci", "sonarqube", "salesforce", "zendesk",
    "hubspot", "freshdesk", "genesys", "five9", "nice cxone",
)


def _cv_text(cv: CVData) -> str:
    parts = [cv.headline, cv.summary, " ".join(cv.skills), " ".join(cv.languages)]
    for exp in cv.experience:
        parts.extend([exp.title, exp.description, " ".join(exp.technologies)])
    return " ".join(parts).lower()


def _limit_sentences(text: str, maximum: int = 2) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(part for part in parts[:maximum] if part).strip()


def sanitize_bpo_adaptation(original: CVData, adapted: CVData) -> CVData:
    """Apply non-negotiable BPO invariants after the AI response."""
    safe = adapted.model_copy(deep=True)
    safe.contact = original.contact
    safe.headline = original.headline
    safe.education = original.education
    safe.languages = original.languages
    safe.certifications = original.certifications
    safe.detected_language = "en"
    safe.summary = _limit_sentences(safe.summary, 2)
    safe.summary = re.sub(r"\bseeking to leverage\b", "bringing", safe.summary, flags=re.I)
    safe.summary = re.sub(
        r"\bfluent in English and Spanish\b",
        "native Spanish and upper-intermediate (B2+) English",
        safe.summary,
        flags=re.I,
    )
    safe.summary = re.sub(
        r"\bfluent English\b",
        "upper-intermediate (B2+) English",
        safe.summary,
        flags=re.I,
    )
    safe.summary = re.sub(r"\.\s+native Spanish", ". Native Spanish", safe.summary)

    original_skill_map = {skill.casefold(): skill for skill in original.skills}
    ordered = []
    for skill in safe.skills:
        canonical = original_skill_map.get(str(skill).casefold())
        if canonical and canonical not in ordered:
            ordered.append(canonical)
    ordered.extend(skill for skill in original.skills if skill not in ordered)
    safe.skills = ordered

    # Preserve verified categories, but order their contents according to the adapted skill order.
    rank = {skill: index for index, skill in enumerate(safe.skills)}
    safe.skill_categories = [category.model_copy(deep=True) for category in original.skill_categories]
    for category in safe.skill_categories:
        category.skills.sort(key=lambda skill: rank.get(skill, len(rank)))

    for index, entry in enumerate(safe.experience):
        source = original.experience[index]
        entry.company = source.company
        entry.title = source.title
        entry.dates = source.dates
        entry.location = source.location
        entry.technologies = source.technologies
        max_bullets = 4 if index == 0 else 3
        bullets = [line.strip() for line in entry.description.splitlines() if line.strip()]
        entry.description = "\n".join(bullets[:max_bullets])
    return safe


def _ordered_verified_skills(original: CVData, adapted: CVData) -> list[str]:
    verified = {skill.casefold(): skill for skill in original.skills}
    ordered: list[str] = []
    for skill in adapted.skills:
        canonical = verified.get(str(skill).casefold())
        if canonical and canonical not in ordered:
            ordered.append(canonical)
    ordered.extend(skill for skill in original.skills if skill not in ordered)
    return ordered


def sanitize_developer_adaptation(original: CVData, adapted: CVData) -> CVData:
    """Keep technical tailoring truthful while allowing concise evidence rewrites."""
    safe = adapted.model_copy(deep=True)
    safe.contact = original.contact
    safe.education = original.education
    safe.languages = original.languages
    safe.certifications = original.certifications
    safe.summary = _limit_sentences(safe.summary, 2)
    safe.skills = _ordered_verified_skills(original, safe)

    # Keep useful AI categories, but remove invented items and ensure every verified
    # skill appears exactly once.
    verified = {skill.casefold(): skill for skill in safe.skills}
    seen: set[str] = set()
    categories = []
    for category in safe.skill_categories:
        kept = []
        for skill in category.skills:
            canonical = verified.get(str(skill).casefold())
            if canonical and canonical.casefold() not in seen:
                kept.append(canonical)
                seen.add(canonical.casefold())
        if kept:
            copied = category.model_copy(deep=True)
            copied.skills = kept
            categories.append(copied)
    remaining = [skill for skill in safe.skills if skill.casefold() not in seen]
    if remaining:
        from app.models.schemas import SkillCategory
        categories.append(SkillCategory(
            name="Otros" if safe.detected_language == "es" else "Additional",
            skills=remaining,
        ))
    safe.skill_categories = categories

    safe.experience = safe.experience[:len(original.experience)]
    for index, source in enumerate(original.experience):
        if index >= len(safe.experience):
            safe.experience.append(source.model_copy(deep=True))
        entry = safe.experience[index]
        entry.company = source.company
        entry.title = source.title
        entry.dates = source.dates
        entry.location = source.location
        entry.technologies = source.technologies
        maximum = 4 if index == 0 else 3
        bullets = [line.strip() for line in entry.description.splitlines() if line.strip()]
        entry.description = "\n".join(bullets[:maximum])

    for index, project in enumerate(safe.projects):
        if index < len(original.projects):
            project.name = original.projects[index].name
            project.url = original.projects[index].url
            project.technologies = original.projects[index].technologies
    return safe


def sanitize_adaptation(original: CVData, adapted: CVData, profile_type: str) -> CVData:
    if profile_type == "bpo":
        return sanitize_bpo_adaptation(original, adapted)
    return sanitize_developer_adaptation(original, adapted)


def review_bpo_claims(original: CVData, adapted: CVData, real_context: str = "") -> ClaimReview:
    """Return a user-visible, deterministic audit of generated claims."""
    source_text = f"{_cv_text(original)} {real_context.lower()}"
    target_text = _cv_text(adapted)
    unsupported = []

    direct_claim = any(pattern.search(target_text) for pattern in DIRECT_EXPERIENCE_PATTERNS)
    if direct_claim:
        unsupported.append("The CV implies direct years of call-center/BPO experience.")

    for term in UNSUPPORTED_TERMS + UNSUPPORTED_METRICS:
        if term in target_text and term not in source_text:
            unsupported.append(f"Unsupported claim or tool: {term}")

    if re.search(r"\bfluent(?:ly)?\b", target_text) and "fluent" not in source_text:
        unsupported.append("The generated text overstates the verified B2+ English level as fluent.")

    protected = (
        adapted.contact == original.contact
        and adapted.education == original.education
        and len(adapted.experience) == len(original.experience)
        and all(
            new.company == old.company
            and new.title == old.title
            and new.dates == old.dates
            and new.location == old.location
            for old, new in zip(original.experience, adapted.experience)
        )
    )
    if not protected:
        unsupported.append("One or more protected identity/employment fields changed.")

    strengths = [
        label for label, signals in TRANSFERABLE_SIGNALS.items()
        if any(signal in target_text for signal in signals)
    ]
    return ClaimReview(
        status="blocked" if unsupported else "passed",
        direct_bpo_experience_claimed=direct_claim,
        unsupported_claims=unsupported,
        protected_fields_preserved=protected,
        transferable_strengths=strengths,
        notes=[
            "No direct call-center/BPO employment is claimed." if not direct_claim else "Direct-experience language requires correction.",
            "Only skills present in the verified BPO base profile are allowed.",
            "Employment titles, employers, dates, education, and language levels are code-protected.",
        ],
    )


def review_developer_claims(original: CVData, adapted: CVData, real_context: str = "") -> ClaimReview:
    source_text = f"{_cv_text(original)} {real_context.lower()}"
    target_text = _cv_text(adapted)
    unsupported = [
        f"Unsupported technology or tool: {term}"
        for term in KNOWN_TECH_TERMS
        if term in target_text and term not in source_text
    ]
    protected = (
        adapted.contact == original.contact
        and adapted.education == original.education
        and adapted.languages == original.languages
        and len(adapted.experience) == len(original.experience)
        and all(
            new.company == old.company
            and new.title == old.title
            and new.dates == old.dates
            and new.location == old.location
            and new.technologies == old.technologies
            for old, new in zip(original.experience, adapted.experience)
        )
        and {skill.casefold() for skill in adapted.skills}
        == {skill.casefold() for skill in original.skills}
    )
    if not protected:
        unsupported.append("One or more protected identity, employment, or skill fields changed.")
    return ClaimReview(
        status="blocked" if unsupported else "passed",
        unsupported_claims=unsupported,
        protected_fields_preserved=protected,
        transferable_strengths=[],
        notes=[
            "Original job titles and per-role technology lists are code-protected.",
            "The verified skill inventory may be reordered but cannot be expanded by AI.",
            "Missing job requirements remain visible instead of being fabricated.",
        ],
    )


def review_claims(
    original: CVData,
    adapted: CVData,
    real_context: str = "",
    profile_type: str = "developer",
) -> ClaimReview:
    if profile_type == "bpo":
        return review_bpo_claims(original, adapted, real_context)
    return review_developer_claims(original, adapted, real_context)

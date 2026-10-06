"""Actionable editorial checks that do not encourage invented accomplishments."""

import re

from app.models.schemas import ATSScore, CVData


_WEAK_START = re.compile(
    r"^(?:[-•*]\s*)?(?:responsible for|helped|worked on|worked with|participated in|"
    r"assisted|involved in|in charge of|responsable de|ayud[eé] a|trabaj[eé] en|"
    r"particip[eé] en|encargado de)\b", re.I,
)
_FILLER = re.compile(r"\b(?:passionate|motivated|results-driven|apasionad[oa]|motivad[oa])\b", re.I)


def editorial_issues(cv: CVData) -> list[str]:
    issues: list[str] = []
    if not cv.summary.strip():
        issues.append("Summary is empty.")
    if _FILLER.search(cv.summary):
        issues.append("Summary contains filler language; replace it with specific evidence.")
    if len(cv.summary) > 550:
        issues.append("Summary is long; keep the strongest two or three sentences.")

    seen: set[str] = set()
    for role_index, role in enumerate(cv.experience):
        bullets = [line.strip() for line in role.description.splitlines() if line.strip()]
        if not bullets:
            issues.append(f"Experience {role_index + 1} has no evidence bullets.")
        for bullet_index, bullet in enumerate(bullets):
            label = f"Experience {role_index + 1}, bullet {bullet_index + 1}"
            if _WEAK_START.search(bullet):
                issues.append(f"{label} starts with a weak opener.")
            if len(bullet) > 250:
                issues.append(f"{label} is over 250 characters; shorten it for scanning.")
            normalized = re.sub(r"\W+", "", bullet.casefold())
            if normalized in seen:
                issues.append(f"{label} repeats another bullet.")
            seen.add(normalized)
    return issues


def evidence_questions(coverage: ATSScore) -> list[str]:
    """Ask for missing facts instead of adding unsupported job terms to the CV."""
    return [
        f"Do you have a real example of {term}? If so, record the employer or project, "
        "what you did, scope, result and source in the master CV before regenerating."
        for term in coverage.missing_keywords[:3]
    ]

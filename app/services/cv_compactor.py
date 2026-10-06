"""Remove the least useful bullet only when the rendered page limit requires it."""

from app.models.schemas import CVData, JobDescription
from app.services.ats_optimizer import _fuzzy_match, _normalize


def compact_one_bullet(cv: CVData, job: JobDescription) -> bool:
    candidates: list[tuple[float, int, int]] = []
    for role_index, role in enumerate(cv.experience):
        bullets = [line for line in role.description.splitlines() if line.strip()]
        minimum = 2 if role_index == 0 else 1
        if len(bullets) <= minimum:
            continue
        for bullet_index, bullet in enumerate(bullets):
            text = _normalize(bullet)
            score = sum(3 for term in job.required_skills if _fuzzy_match(term, text))
            score += sum(2 for term in job.preferred_skills if _fuzzy_match(term, text))
            score += sum(1 for term in job.keywords if _fuzzy_match(term, text))
            score += 0.25 if any(char.isdigit() for char in bullet) else 0
            score += 0.01 * (len(bullets) - bullet_index)
            candidates.append((score, role_index, bullet_index))
    if not candidates:
        return False
    _, role_index, bullet_index = min(candidates)
    bullets = [line for line in cv.experience[role_index].description.splitlines() if line.strip()]
    del bullets[bullet_index]
    cv.experience[role_index].description = "\n".join(bullets)
    return True

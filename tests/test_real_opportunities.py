from pathlib import Path

import fitz

from app.services.base_cv_store import get_profile_definition, load_base_cv
from app.services.claim_guard import sanitize_adaptation, review_claims
from app.services.opportunity_store import list_opportunities
from app.services.pdf_generator import generate_pdf_from_template


def test_catalog_has_two_active_real_jobs_per_profile():
    items = list_opportunities()
    assert len(items) == 4
    for profile_id in ("developer", "bilingual_customer_service"):
        matching = [item for item in items if item.profile_id == profile_id]
        assert len(matching) == 2
        assert all(item.status == "active" for item in matching)
        assert all(item.source_name == "LinkedIn" for item in matching)
        assert all(item.source_url.startswith("https://") for item in matching)
        assert all(item.checked_at == "2026-08-31" for item in matching)


def test_developer_truth_guard_restores_titles_technologies_and_skills():
    original = load_base_cv("developer").cv
    unsafe = original.model_copy(deep=True)
    unsafe.experience[0].title = "Senior Python Engineer"
    unsafe.experience[0].technologies = ["Ruby on Rails", "Azure"]
    unsafe.skills = ["Ruby on Rails", "Azure", "Python"]

    safe = sanitize_adaptation(original, unsafe, profile_type="developer")
    assert safe.experience[0].title == original.experience[0].title
    assert safe.experience[0].technologies == original.experience[0].technologies
    assert {skill.casefold() for skill in safe.skills} == {
        skill.casefold() for skill in original.skills
    }
    assert review_claims(original, safe, profile_type="developer").status == "passed"


def test_technical_template_is_available_and_profile_targets_one_page():
    profile = get_profile_definition("developer")
    assert profile.default_template == "technical"
    assert profile.max_pages == 1

    cv = load_base_cv("developer").cv.model_copy(deep=True)
    for index, entry in enumerate(cv.experience):
        entry.description = "\n".join(entry.description.splitlines()[: (4 if index == 0 else 3)])
    output = generate_pdf_from_template(
        cv,
        template_name="technical",
        job_title="Template Test",
        max_pages=1,
    )
    try:
        with fitz.open(output) as document:
            assert document.page_count == 1
            text = "".join(page.get_text() for page in document)
        assert "Santiago Hurtado Lopez" in text
        assert "Bit Colombia" in text
        ordered = text.casefold()
        assert ordered.index("perfil profesional") < ordered.index("experiencia profesional")
        assert ordered.index("experiencia profesional") < ordered.index("educación")
        assert ordered.index("educación") < ordered.index("competencias técnicas")
    finally:
        Path(output).unlink(missing_ok=True)

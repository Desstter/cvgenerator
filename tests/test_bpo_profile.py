import fitz
import pytest
from fastapi.testclient import TestClient

from app.models.schemas import JobDescription
from app.prompts.system_prompt import BPO_SYSTEM_PROMPT
from app.services.ats_optimizer import analyze_keyword_match
from app.services.base_cv_store import (
    get_profile_definition,
    list_profile_definitions,
    load_base_cv,
    save_base_cv,
)
from app.services.claim_guard import sanitize_bpo_adaptation, review_bpo_claims
from app.services.pdf_generator import generate_pdf_from_template
from app.main import app
from app.services.ai_adapter import AIProvider, analyze_and_adapt


def test_profiles_are_independent_and_discoverable():
    profiles = {profile.id: profile for profile in list_profile_definitions()}
    assert set(profiles) == {"developer", "bilingual_customer_service"}
    assert profiles["bilingual_customer_service"].one_page_required is True

    developer = load_base_cv("developer")
    bilingual = load_base_cv("bilingual_customer_service")
    assert developer.profile_type == "developer"
    assert bilingual.profile_type == "bpo"
    assert developer.cv.summary != bilingual.cv.summary
    assert developer.cv.contact.github
    assert bilingual.cv.contact.github == ""


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="Unknown CV profile"):
        get_profile_definition("not-a-profile")


def test_profile_store_cannot_overwrite_a_different_profile():
    bilingual = load_base_cv("bilingual_customer_service")
    with pytest.raises(ValueError, match="does not match"):
        save_base_cv(bilingual, "developer")


def test_profile_api_exposes_both_profiles_and_rejects_unknown_profile():
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/profiles")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {
        "developer", "bilingual_customer_service"
    }
    assert client.get("/api/base-cv-data?profile=missing").status_code == 400


def test_bpo_base_is_honest_and_in_english():
    cv = load_base_cv("bilingual_customer_service").cv
    assert cv.detected_language == "en"
    assert "B2+" in " ".join(cv.languages)
    assert "over three years of experience in remote" in cv.summary.lower()
    assert "five years of customer service" not in cv.summary.lower()
    assert all("customer service" not in exp.title.lower() for exp in cv.experience)
    assert all(not exp.technologies for exp in cv.experience)


def test_sanitizer_preserves_protected_fields_and_removes_unverified_skills():
    original = load_base_cv("bilingual_customer_service").cv
    generated = original.model_copy(deep=True)
    generated.experience[0].title = "Senior Customer Service Representative"
    generated.experience[0].technologies = ["Salesforce"]
    generated.experience[0].description += "\n• Unsupported fifth bullet."
    generated.skills = ["Salesforce", "Bilingual Communication"]
    generated.languages = ["English (C1)"]

    safe = sanitize_bpo_adaptation(original, generated)
    assert safe.experience[0].title == original.experience[0].title
    assert safe.experience[0].technologies == []
    assert len(safe.experience[0].description.splitlines()) == 4
    assert "Salesforce" not in safe.skills
    assert safe.languages == original.languages


def test_claim_guard_blocks_direct_bpo_experience_and_unsupported_tools():
    original = load_base_cv("bilingual_customer_service").cv
    unsafe = original.model_copy(deep=True)
    unsafe.summary = "Customer service professional with 5 years of experience in customer service using Salesforce."
    review = review_bpo_claims(original, unsafe)
    assert review.status == "blocked"
    assert review.direct_bpo_experience_claimed is True
    assert any("salesforce" in claim for claim in review.unsupported_claims)


def test_claim_guard_passes_verified_base_profile():
    store = load_base_cv("bilingual_customer_service")
    review = review_bpo_claims(store.cv, store.cv)
    assert review.status == "passed"
    assert review.protected_fields_preserved is True
    assert review.direct_bpo_experience_claimed is False


def test_bpo_ai_adapter_code_protects_titles_technologies_and_language():
    store = load_base_cv("bilingual_customer_service")

    class FakeProvider(AIProvider):
        last_system = ""

        def chat(self, system: str, user: str) -> str:
            raise AssertionError("chat_json should be used")

        def chat_json(self, system: str, user: str, schema=None) -> dict:
            self.last_system = system
            return {
                "job_analysis": {
                    "title": "Customer Service Representative",
                    "company": "Example BPO",
                    "required_skills": ["English", "Customer Service"],
                    "preferred_skills": ["Salesforce"],
                    "keywords": ["Communication Skills"],
                    "responsibilities": ["Assist customers"],
                    "detected_language": "es",
                },
                "keyword_equivalences": [],
                "adapted_cv": {
                    "summary": store.cv.summary,
                    "skills": ["Salesforce", *store.cv.skills],
                    "skill_categories": [],
                    "experience": [
                        {
                            "title": "Customer Service Representative",
                            "description": entry.description,
                            "technologies": ["Salesforce"],
                        }
                        for entry in store.cv.experience
                    ],
                    "projects": [],
                },
            }

    provider = FakeProvider()
    _, adapted, _ = analyze_and_adapt(
        provider,
        store.cv,
        "Representante bilingüe de servicio al cliente",
        profile_type="bpo",
    )
    assert adapted.detected_language == "en"
    assert [entry.title for entry in adapted.experience] == [
        entry.title for entry in store.cv.experience
    ]
    assert all(not entry.technologies for entry in adapted.experience)
    assert "no direct call-center or bpo employment" in provider.last_system.lower()


def test_bpo_ats_suggestions_never_tell_user_to_add_unsupported_skill():
    cv = load_base_cv("bilingual_customer_service").cv
    job = JobDescription(raw_text="", required_skills=["Salesforce"])
    result = analyze_keyword_match(cv, job, profile_type="bpo")
    text = " ".join(result.suggestions).lower()
    assert "add required skills" not in text
    assert "only if" in text


def test_bpo_prompt_contains_non_negotiable_truth_guards():
    prompt = BPO_SYSTEM_PROMPT.lower()
    assert "no direct call-center or bpo employment" in prompt
    assert "never claim years of customer service" in prompt
    assert "do not rename development jobs" in prompt
    assert "entire cv must remain in english" in prompt


def test_bilingual_template_is_exactly_one_page(tmp_path, monkeypatch):
    from app.services import pdf_generator

    monkeypatch.setattr(pdf_generator.settings, "outputs_dir", tmp_path)
    cv = load_base_cv("bilingual_customer_service").cv
    path = generate_pdf_from_template(
        cv,
        template_name="bilingual",
        job_title="Bilingual Customer Service",
        max_pages=1,
    )
    assert path.exists() and path.stat().st_size > 0
    with fitz.open(path) as document:
        assert document.page_count == 1
        text = " ".join(page.get_text() for page in document)
    assert "Bilingual Customer Service" in text
    assert "Software Programming Technician" in text
    assert "Technologies:" not in text
    ordered = text.casefold()
    assert ordered.index("professional summary") < ordered.index("professional experience")
    assert ordered.index("professional experience") < ordered.index("education")
    assert ordered.index("education") < ordered.index("core skills")


def test_unknown_template_is_rejected():
    cv = load_base_cv("bilingual_customer_service").cv
    with pytest.raises(ValueError, match="Unknown PDF template"):
        generate_pdf_from_template(cv, template_name="../../secret")

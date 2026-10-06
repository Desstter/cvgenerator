"""Regression checks for claims and final artifacts that can mislead a user."""

from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import (BaseCVStore, CVData, ContactInfo, EvidenceFact,
                                ExperienceContextEntry, ExperienceEntry, JobDescription, ProjectEntry)
from app.services.claim_guard import review_claims, sanitize_adaptation
from app.services.base_cv_store import build_real_context
from app.services.cv_compactor import compact_one_bullet
from app.services.cv_quality import editorial_issues, evidence_questions
from app.services.pdf_generator import verify_pdf_content


def test_new_metrics_are_blocked_per_role():
    original = CVData(experience=[ExperienceEntry(company="A", title="Developer", description="Built a platform.")])
    adapted = original.model_copy(deep=True)
    adapted.experience[0].description = "Built a platform for 12 million users and cut cost by 80%."
    review = review_claims(original, adapted)
    assert review.status == "blocked"
    assert any("80%" in reason for reason in review.unsupported_claims)


def test_lower_experience_bound_is_supported_by_source():
    original = CVData(summary="Developer with 5 años de experiencia.")
    adapted = original.model_copy(deep=True)
    adapted.summary = "Developer with 3+ years of experience."
    review = review_claims(original, adapted)
    assert review.status == "needs_review"
    assert not review.unsupported_claims


def test_written_number_does_not_hide_direct_bpo_experience_claim():
    original = CVData(summary="Professional software experience.")
    adapted = original.model_copy(deep=True)
    adapted.summary = "Five years of experience in customer service."
    review = review_claims(original, adapted, profile_type="bpo")
    assert review.status == "blocked"
    assert review.direct_bpo_experience_claimed


def test_only_verified_structured_facts_enter_model_context():
    store = BaseCVStore(experience_context={"Acme": ExperienceContextEntry(facts=[
        EvidenceFact(action="Built an API", metric="40%", verified=True),
        EvidenceFact(action="Unconfirmed project", verified=False),
    ])})
    context = build_real_context(store)
    assert "Built an API" in context
    assert "Unconfirmed project" not in context


def test_project_rewrite_requires_review_and_preserves_technology():
    original = CVData(projects=[ProjectEntry(name="P", description="Built a Python prototype.", technologies=["Python"])])
    adapted = original.model_copy(deep=True)
    adapted.projects[0].description = "Built a Python prototype for a logistics team."
    adapted.projects[0].technologies = ["AWS"]
    safe = sanitize_adaptation(original, adapted, "developer")
    review = review_claims(original, safe)
    assert safe.projects[0].technologies == ["Python"]
    assert review.status == "needs_review"
    assert review.review_items[0]["field"] == "projects.0"


def test_pdf_readback_rejects_missing_content(tmp_path: Path):
    path = tmp_path / "incomplete.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Ana Example")
    doc.save(path)
    doc.close()
    cv = CVData(contact=ContactInfo(name="Ana Example"), summary="Built a verified service.")
    with pytest.raises(ValueError, match="lost or changed content"):
        verify_pdf_content(path, cv, "technical", 1)


def test_pdf_readback_preserves_wrapped_degree_with_positioned_dates(tmp_path, monkeypatch):
    from app.models.schemas import EducationEntry
    from app.services import pdf_generator

    monkeypatch.setattr(pdf_generator.settings, "outputs_dir", tmp_path)
    cv = CVData(contact=ContactInfo(name="Ana Example", email="ana@example.com"),
                education=[EducationEntry(institution="Example Institute",
                                          degree="Técnico en Programación de Software",
                                          dates="Sep 2017 - Ene 2020")], detected_language="en")
    path = pdf_generator.generate_pdf_from_template(cv, template_name="modern")
    verify_pdf_content(path, cv, "modern")


def test_pdf_failure_is_not_misreported_as_ai_rate_limit(monkeypatch):
    from app import main

    def broken_provider(*args, **kwargs):
        raise ValueError("Generated PDF lost or changed content")

    monkeypatch.setattr(main, "get_provider", broken_provider)
    client = TestClient(app)
    response = client.post("/api/adapt", data={"job_description": "Python developer"})
    assert response.status_code == 500
    assert "rate limit" not in str(response.json()).lower()


def test_compaction_preserves_the_required_skill_bullet():
    cv = CVData(experience=[ExperienceEntry(
        company="A", title="Developer",
        description="Built a React application.\nUpdated internal documentation.\nImproved the React interface.",
    )])
    job = JobDescription(raw_text="", required_skills=["React"])
    assert compact_one_bullet(cv, job)
    assert "documentation" not in cv.experience[0].description
    assert "React" in cv.experience[0].description


def test_editorial_checks_flag_weak_or_repeated_bullets():
    cv = CVData(summary="Passionate developer", experience=[ExperienceEntry(
        description="Responsible for testing.\nResponsible for testing.",
    )])
    issues = editorial_issues(cv)
    assert any("filler" in issue for issue in issues)
    assert any("weak opener" in issue for issue in issues)
    assert any("repeats" in issue for issue in issues)


def test_missing_requirement_produces_an_evidence_question():
    from app.models.schemas import ATSScore
    questions = evidence_questions(ATSScore(missing_keywords=["Kubernetes"]))
    assert "Kubernetes" in questions[0]
    assert "source" in questions[0]


def test_unreviewed_saved_pdf_cannot_be_downloaded(tmp_path: Path, monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings, "outputs_dir", tmp_path)
    monkeypatch.setattr(main.settings, "saved_dir", tmp_path)
    monkeypatch.setattr(main, "load_history", lambda: [{"pdf_filename": "pending.pdf", "reviewed": False}])
    (tmp_path / "pending.pdf").write_bytes(b"pdf")
    client = TestClient(app)
    assert client.get("/api/download/pending.pdf").status_code == 409


def test_unconfirmed_upload_is_rejected_before_adaptation():
    client = TestClient(app)
    response = client.post("/api/adapt", data={"job_description": "Python developer"},
                           files={"file": ("resume.pdf", b"fake", "application/pdf")})
    assert response.status_code == 400
    assert "confirm" in str(response.json()).lower()


def test_invalid_request_does_not_start_ai(monkeypatch):
    from app import main

    def unexpected_provider(*args):
        pytest.fail("Invalid requests must be rejected before calling the AI provider")

    monkeypatch.setattr(main, "get_provider", unexpected_provider)
    client = TestClient(app)
    assert client.post("/api/adapt", data={"job_description": "   "}).status_code == 400
    assert client.post("/api/adapt", data={"job_description": "Developer", "template": "original"}).status_code == 400


def test_corrupt_profile_never_falls_back_to_another_identity(tmp_path, monkeypatch):
    from app.services import base_cv_store

    path = tmp_path / "base_cv.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setitem(base_cv_store.PROFILE_FILES, "developer", path)
    with pytest.raises(ValueError, match="CV data file is invalid"):
        base_cv_store.load_base_cv("developer")
    assert path.read_text(encoding="utf-8") == "{broken"


def test_pdf_readback_rejects_missing_skills_and_education(tmp_path):
    from app.models.schemas import EducationEntry

    path = tmp_path / "missing-details.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "Ana Example")
    doc.save(path)
    doc.close()
    cv = CVData(contact=ContactInfo(name="Ana Example"), skills=["Python"],
                education=[EducationEntry(institution="Example Institute", degree="Software Technology")])
    with pytest.raises(ValueError, match="Python"):
        verify_pdf_content(path, cv, "technical", 1)


def test_cv_html_is_rendered_as_literal_text(tmp_path, monkeypatch):
    from app.services import pdf_generator

    monkeypatch.setattr(pdf_generator.settings, "outputs_dir", tmp_path)
    cv = CVData(contact=ContactInfo(name="Ana Example", email="ana@example.com"),
                summary="Built <b>services</b> with Python & SQL.")
    path = pdf_generator.generate_pdf_from_template(cv, template_name="technical")
    with fitz.open(path) as document:
        text = "".join(page.get_text() for page in document)
    assert "<b>services</b>" in text
    assert "Python & SQL" in text


def test_adapt_review_confirm_and_revise_flow(tmp_path: Path, monkeypatch):
    from app import main
    from app.services import history
    from app.services.base_cv_store import load_base_cv

    class FakeProvider:
        model = "fixture"

        def chat_json(self, system, user, schema=None):
            cv = load_base_cv("bilingual_customer_service").cv
            return {
                "job_analysis": {
                    "title": "Bilingual Customer Service", "company": "Example",
                    "required_skills": ["English"], "preferred_skills": [],
                    "keywords": ["communication"], "responsibilities": [],
                    "detected_language": "en",
                },
                "keyword_equivalences": [],
                "adapted_cv": {
                    "summary": cv.summary.replace("coordinating teams", "working across teams"),
                    "skills": cv.skills,
                    "skill_categories": [item.model_dump() for item in cv.skill_categories],
                    "experience": [
                        {"title": item.title, "description": item.description, "technologies": item.technologies}
                        for item in cv.experience
                    ],
                    "projects": [],
                },
            }

    monkeypatch.setattr(main, "get_provider", lambda name=None: FakeProvider())
    monkeypatch.setattr(main.settings, "refine_pass", False)
    monkeypatch.setattr(main.settings, "outputs_dir", tmp_path)
    monkeypatch.setattr(main.settings, "saved_dir", tmp_path)
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.json")
    client = TestClient(app)
    response = client.post("/api/adapt", data={
        "job_description": "Bilingual customer service role requiring English communication.",
        "profile_id": "bilingual_customer_service", "template": "bilingual",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["claim_review"]["status"] == "needs_review"
    assert client.get("/api/download/" + result["pdf_filename"]).status_code == 409
    saved = client.get("/api/history/" + result["record_id"]).json()
    assert saved["snapshot"]["adapted_cv"]["summary"] == result["adapted_cv"]["summary"]

    edited = result["adapted_cv"]
    invalid_skills = {**edited, "skills": [*edited["skills"], "Imaginary CRM"]}
    rejected = client.post(f"/api/history/{result['record_id']}/revise", json=invalid_skills)
    assert rejected.status_code == 422
    edited["summary"] = edited["summary"].replace("working across teams", "coordinating teams")
    revised = client.post(f"/api/history/{result['record_id']}/revise", json=edited)
    assert revised.status_code == 200, revised.text
    assert revised.json()["record_id"] != result["record_id"]
    assert client.post(f"/api/history/{result['record_id']}/confirm", json={"fields": []}).status_code == 422
    fields = [item["field"] for item in result["claim_review"]["review_items"]]
    assert client.post(f"/api/history/{result['record_id']}/confirm", json={"fields": fields}).status_code == 200
    assert client.get("/api/download/" + result["pdf_filename"]).status_code == 200
    assert client.put(f"/api/history/{result['record_id']}/feedback", json={"outcome": "interview"}).status_code == 200
    assert client.get(f"/api/history/{result['record_id']}").json()["outcome"] == "interview"

"""Tests for recruiter-facing PDF filenames and skill-category parsing."""
from app.models.schemas import CVData, ContactInfo, SkillCategory
from app.services.pdf_generator import _slugify, _build_filename


# ── PDF filename ─────────────────────────────────────────────────────────────

def test_slugify_strips_accents_and_symbols():
    assert _slugify("Desarrollador Backend (Python/Django)") == "Desarrollador_Backend_Python_Django"
    assert _slugify("José Pérez") == "Jose_Perez"


def test_build_filename_with_name_and_title():
    cv = CVData(contact=ContactInfo(name="Ana María Gómez"))
    first = _build_filename(cv, "Backend Developer")
    second = _build_filename(cv, "Backend Developer")
    assert first.startswith("CV_Ana_Maria_Gomez_Backend_Developer_")
    assert first.endswith(".pdf")
    assert first != second


def test_build_filename_without_title():
    cv = CVData(contact=ContactInfo(name="Ana Gómez"))
    assert _build_filename(cv).startswith("CV_Ana_Gomez_")


def test_build_filename_empty_falls_back_to_unique():
    name = _build_filename(CVData())
    assert name.startswith("CV_") and name.endswith(".pdf") and len(name) > 10


# ── skill categories ─────────────────────────────────────────────────────────

def test_skill_categories_model_roundtrip():
    cv = CVData(skill_categories=[SkillCategory(name="Languages", skills=["Python", "Go"])])
    dumped = cv.model_dump()
    assert dumped["skill_categories"][0] == {"name": "Languages", "skills": ["Python", "Go"]}

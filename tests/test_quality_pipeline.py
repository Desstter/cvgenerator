"""Tests for the quality-pipeline additions: equivalence coercion (list + legacy dict
formats), recruiter-facing PDF filenames, and skill-category parsing."""
from app.models.schemas import CVData, ContactInfo, SkillCategory
from app.services.ai_adapter import _coerce_equivalences
from app.services.pdf_generator import _slugify, _build_filename


# ── _coerce_equivalences ─────────────────────────────────────────────────────

def test_equivalences_list_format():
    raw = [
        {"term": "React", "equivalents": ["ReactJS", "React.js"]},
        {"term": "CI/CD", "equivalents": ["GitHub Actions"]},
    ]
    assert _coerce_equivalences(raw) == {
        "React": ["ReactJS", "React.js"],
        "CI/CD": ["GitHub Actions"],
    }


def test_equivalences_legacy_dict_format():
    assert _coerce_equivalences({"React": ["ReactJS"]}) == {"React": ["ReactJS"]}


def test_equivalences_malformed_entries_dropped():
    raw = [
        {"term": "React", "equivalents": ["ReactJS"]},
        {"equivalents": ["orphan"]},          # no term
        "not a dict",
        {"term": "", "equivalents": ["x"]},   # empty term
    ]
    assert _coerce_equivalences(raw) == {"React": ["ReactJS"]}


def test_equivalences_garbage_returns_empty():
    assert _coerce_equivalences(None) == {}
    assert _coerce_equivalences("nope") == {}
    assert _coerce_equivalences(42) == {}


# ── PDF filename ─────────────────────────────────────────────────────────────

def test_slugify_strips_accents_and_symbols():
    assert _slugify("Desarrollador Backend (Python/Django)") == "Desarrollador_Backend_Python_Django"
    assert _slugify("José Pérez") == "Jose_Perez"


def test_build_filename_with_name_and_title():
    cv = CVData(contact=ContactInfo(name="Ana María Gómez"))
    assert _build_filename(cv, "Backend Developer") == "CV_Ana_Maria_Gomez_Backend_Developer.pdf"


def test_build_filename_without_title():
    cv = CVData(contact=ContactInfo(name="Ana Gómez"))
    assert _build_filename(cv) == "CV_Ana_Gomez.pdf"


def test_build_filename_empty_falls_back_to_unique():
    name = _build_filename(CVData())
    assert name.startswith("CV_") and name.endswith(".pdf") and len(name) > 10


# ── skill categories ─────────────────────────────────────────────────────────

def test_skill_categories_model_roundtrip():
    cv = CVData(skill_categories=[SkillCategory(name="Languages", skills=["Python", "Go"])])
    dumped = cv.model_dump()
    assert dumped["skill_categories"][0] == {"name": "Languages", "skills": ["Python", "Go"]}

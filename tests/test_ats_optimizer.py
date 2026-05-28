"""Tests for the ATS keyword matching, scoring, and skill reordering.

Goals:
- Ensure analyze_keyword_match and reorder_skills agree on what counts as a "match".
- Cover exact / synonym / fuzzy / LLM-equivalence paths.
- Verify weighted score math (required ×3, preferred ×2, general ×1).
"""
from app.models.schemas import CVData, ContactInfo, ExperienceEntry, JobDescription
from app.services.ats_optimizer import (
    _fuzzy_match,
    _expand_with_synonyms,
    analyze_keyword_match,
    reorder_skills,
)


def _make_cv(skills=None, summary="", experience=None) -> CVData:
    return CVData(
        contact=ContactInfo(name="Test"),
        summary=summary,
        skills=skills or [],
        experience=experience or [],
    )


def _make_job(required=None, preferred=None, keywords=None) -> JobDescription:
    return JobDescription(
        raw_text="",
        required_skills=required or [],
        preferred_skills=preferred or [],
        keywords=keywords or [],
    )


# ── _fuzzy_match ─────────────────────────────────────────────────────────────

def test_fuzzy_exact_match():
    assert _fuzzy_match("React", "i love react") is True


def test_fuzzy_case_insensitive():
    assert _fuzzy_match("REACT", "react developer") is True


def test_fuzzy_synonym_short_to_long():
    # CV has "machine learning", job asks for "ML"
    assert _fuzzy_match("ML", "skilled in machine learning") is True


def test_fuzzy_synonym_long_to_short():
    # CV has "ml", job asks for "Machine Learning"
    assert _fuzzy_match("Machine Learning", "expert in ml") is True


def test_fuzzy_javascript_js():
    # JS ↔ JavaScript both directions
    assert _fuzzy_match("JS", "javascript developer") is True
    assert _fuzzy_match("JavaScript", "js ninja") is True


def test_fuzzy_typescript_ts():
    assert _fuzzy_match("TS", "typescript pro") is True
    assert _fuzzy_match("TypeScript", "ts dev") is True


def test_fuzzy_reactjs_normalizes():
    assert _fuzzy_match("ReactJS", "react developer") is True
    assert _fuzzy_match("React.js", "react") is True


def test_fuzzy_no_match():
    assert _fuzzy_match("Kotlin", "python developer") is False


def test_fuzzy_llm_equivalence_used():
    # LLM says "k8s ≡ kubernetes orchestration" for this session
    extra = {"Kubernetes": ["k8s", "container orchestration"]}
    assert _fuzzy_match("Kubernetes", "experienced with k8s", extra) is True
    assert _fuzzy_match("k8s", "deep kubernetes background", extra) is True


def test_fuzzy_word_typo_fuzzy_fallback():
    # SequenceMatcher path for >3-char tokens
    assert _fuzzy_match("Postgres", "postgrs database admin") is True


def test_fuzzy_short_tokens_dont_trigger_fuzzy():
    # 3-char-or-less tokens skip fuzzy to avoid noise
    assert _fuzzy_match("Go", "no programming background") is False


# ── _expand_with_synonyms ────────────────────────────────────────────────────

def test_expand_includes_self():
    assert "react" in _expand_with_synonyms("React")


def test_expand_pulls_synonym_map():
    variants = _expand_with_synonyms("React.js")
    assert "react" in variants


def test_expand_pulls_llm_equivalence():
    variants = _expand_with_synonyms("Kubernetes", {"Kubernetes": ["k8s"]})
    assert "k8s" in variants


def test_expand_llm_equivalence_bidirectional():
    # If LLM maps canonical → equivalents, asking for an equivalent also expands to canonical
    variants = _expand_with_synonyms("k8s", {"Kubernetes": ["k8s"]})
    assert "kubernetes" in variants


# ── analyze_keyword_match ────────────────────────────────────────────────────

def test_score_zero_when_no_keywords_match():
    cv = _make_cv(skills=["Python"])
    job = _make_job(required=["Rust"], preferred=["Go"], keywords=["Kotlin"])
    result = analyze_keyword_match(cv, job)
    assert result.overall_score == 0.0
    assert result.required_score == 0.0
    assert set(result.missing_keywords) == {"Rust", "Go", "Kotlin"}


def test_score_perfect_when_everything_matches():
    cv = _make_cv(skills=["React", "TypeScript", "Node.js"])
    job = _make_job(required=["React"], preferred=["TypeScript"], keywords=["Node.js"])
    result = analyze_keyword_match(cv, job)
    assert result.overall_score == 100.0
    assert result.missing_keywords == []


def test_score_weighting_required_counts_triple():
    # Only the required keyword matches. With weights 3/2/1:
    # matched = 3, total = 3 + 2 + 1 = 6 → 50%
    cv = _make_cv(skills=["React"])
    job = _make_job(required=["React"], preferred=["Vue"], keywords=["Svelte"])
    result = analyze_keyword_match(cv, job)
    assert result.overall_score == 50.0
    assert result.required_score == 100.0
    assert result.preferred_score == 0.0


def test_score_uses_llm_equivalences():
    cv = _make_cv(skills=["k8s"])
    job = _make_job(required=["Kubernetes"])
    # Without equivalences: k8s ≡ kubernetes is in the static map already, so this still passes.
    # With equivalences for a custom term the static map does not cover:
    cv2 = _make_cv(skills=["Vertex AI"])
    job2 = _make_job(required=["Google Cloud ML Platform"])
    assert analyze_keyword_match(cv2, job2).overall_score == 0.0
    enriched = analyze_keyword_match(
        cv2, job2, extra_synonyms={"Google Cloud ML Platform": ["Vertex AI"]}
    )
    assert enriched.overall_score == 100.0


def test_score_handles_empty_job():
    cv = _make_cv(skills=["Anything"])
    job = _make_job()
    result = analyze_keyword_match(cv, job)
    assert result.overall_score == 0


def test_cv_text_includes_experience_descriptions():
    cv = _make_cv(
        experience=[ExperienceEntry(
            company="X", title="Eng", description="Built ML pipelines for fraud detection",
            technologies=["Python"],
        )],
    )
    job = _make_job(required=["Machine Learning"])
    assert analyze_keyword_match(cv, job).overall_score == 100.0


# ── reorder_skills (must agree with the matcher) ─────────────────────────────

def test_reorder_puts_matching_first():
    skills = ["Excel", "Python", "Word"]
    result = reorder_skills(skills, ["Python"])
    assert result == ["Python", "Excel", "Word"]


def test_reorder_uses_synonyms_consistently():
    # ReactJS in CV must move to front when job asks for React
    skills = ["Excel", "ReactJS"]
    result = reorder_skills(skills, ["React"])
    assert result[0] == "ReactJS"


def test_reorder_uses_llm_equivalences():
    skills = ["Excel", "Vertex AI"]
    result = reorder_skills(
        skills, ["Google Cloud ML Platform"],
        extra_synonyms={"Google Cloud ML Platform": ["Vertex AI"]},
    )
    assert result[0] == "Vertex AI"


def test_reorder_and_match_agree_on_synonyms():
    """Critical invariant: every skill that is matched by analyze_keyword_match
    must be moved to the front by reorder_skills."""
    skills = ["Excel", "JavaScript", "Word"]
    job = _make_job(required=["JS"])
    cv = _make_cv(skills=skills)
    match_result = analyze_keyword_match(cv, job)
    # JS should appear in matched_keywords because CV has JavaScript
    assert "JS" in match_result.matched_keywords
    # …and reorder_skills should hoist JavaScript to the front
    reordered = reorder_skills(skills, ["JS"])
    assert reordered[0] == "JavaScript"


def test_reorder_preserves_relative_order():
    skills = ["A", "Python", "B", "React", "C"]
    result = reorder_skills(skills, ["Python", "React"])
    # Matching skills come first, preserving their original relative order
    assert result == ["Python", "React", "A", "B", "C"]


def test_reorder_no_matches_keeps_order():
    skills = ["A", "B", "C"]
    assert reorder_skills(skills, ["XYZ"]) == ["A", "B", "C"]

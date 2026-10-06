"""Observable CLI workflows, using isolated candidates and no external AI calls."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli import canonical_url


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = {
    "profile_id": "developer", "display_name": "Developer", "profile_type": "developer",
    "cv": {
        "contact": {"name": "Ana Example", "email": "ana@example.com", "location": "Cali, Colombia"},
        "headline": "Software Developer", "summary": "Built Python APIs for an internal service.",
        "experience": [{"company": "Example", "title": "Developer", "dates": "2022 - 2025",
                        "description": "Built Python APIs for an internal service.", "technologies": ["Python"]}],
        "education": [{"institution": "Example Institute", "degree": "Software Technology", "dates": "2021"}],
        "skills": ["Python"], "languages": ["Spanish Native"], "detected_language": "en",
    }, "experience_context": {},
}


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def run_cli(workspace, *arguments, ok=True):
    result = subprocess.run([sys.executable, "-m", "app.cli", "--workspace", str(workspace), *map(str, arguments)],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=90)
    if ok:
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    assert result.returncode != 0
    return result.stderr


@pytest.fixture
def workspace(tmp_path):
    candidate = save(tmp_path / "candidate.json", CANDIDATE)
    root = tmp_path / "workspace"
    run_cli(root, "init", "--candidate", candidate)
    return root


def generate_fixture(workspace, changed=True, repo=ROOT):
    job = workspace / "job.txt"
    job.write_text("Python developer for Example", encoding="utf-8")
    # Exercise the actual pipeline and renderer while replacing only the external AI.
    script = '''
import sys, json
from app.cli import configure_workspace, main
configure_workspace(sys.argv[1])
from app import main as api
from app.models.schemas import JobDescription
from app.services.base_cv_store import load_base_cv
api.settings.refine_pass = False
api.get_provider = lambda name=None: type("Fixture", (), {"model": "offline-fixture"})()
def adapt(provider, cv, text, **kwargs):
    out = cv.model_copy(deep=True)
    if sys.argv[2] == "changed":
        out.summary = "Developed Python APIs for an internal service."
    return JobDescription(raw_text=text, title="Python Developer", company="Example", required_skills=["Python"], detected_language="en"), out
api.analyze_and_adapt = adapt
raise SystemExit(main(["--workspace", sys.argv[1], "generate", "--job", sys.argv[3]]))
'''
    result = subprocess.run([sys.executable, "-c", script, str(workspace), "changed" if changed else "same", str(job)],
                            cwd=repo, capture_output=True, text=True, encoding="utf-8", timeout=90)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_missing_or_invalid_candidate_never_uses_packaged_identity(tmp_path):
    assert "Initialize this candidate" in run_cli(tmp_path / "empty", "profile", ok=False)
    invalid = save(tmp_path / "invalid.json", {"profile_id": "developer", "cv": {}})
    assert "Invalid candidate" in run_cli(tmp_path / "bad", "init", "--candidate", invalid, ok=False)
    assert not (tmp_path / "bad" / "data" / "base_cv.json").exists()


def test_isolated_identity_and_profile_updates(workspace, tmp_path):
    assert run_cli(workspace, "profile")["cv"]["contact"]["name"] == "Ana Example"
    changed = json.loads(json.dumps(CANDIDATE))
    changed["cv"]["contact"]["name"] = "Other Person"
    path = save(tmp_path / "other.json", changed)
    assert "another identity" in run_cli(workspace, "profile-update", "--candidate", path, ok=False)
    changed = json.loads(json.dumps(CANDIDATE))
    changed["cv"]["skills"].append("SQL")
    save(path, changed)
    assert run_cli(workspace, "profile-update", "--candidate", path)["updated"]
    assert list((workspace / "data" / "revisions").glob("*.json"))


def test_generate_inspect_evidence_review_export_and_revise(workspace):
    generated = generate_fixture(workspace)
    record = generated["record_id"]
    assert generated["claim_review"]["status"] == "needs_review"
    report = run_cli(workspace, "inspect", "--record", record)
    assert report["quality"]["pdf_valid"]
    assert "before downloading" in run_cli(workspace, "export", "--record", record, "--out", workspace / "ready.pdf", ok=False)
    review = report["review_template"]
    review["reviewer"] = "Fixture reviewer"
    review["decisions"][0].update(decision="supported", evidence_quote="No evidence", reason="same meaning")
    review_path = save(workspace / "review.json", review)
    assert "exact evidence quote" in run_cli(workspace, "confirm", "--record", record, "--review", review_path, ok=False)
    review["decisions"][0]["evidence_quote"] = CANDIDATE["cv"]["summary"]
    save(review_path, review)
    assert run_cli(workspace, "confirm", "--record", record, "--review", review_path)["reviewed"]
    exported = run_cli(workspace, "export", "--record", record, "--out", workspace / "ready.pdf")
    assert len(exported["sha256"]) == 64
    assert "already exists" in run_cli(workspace, "export", "--record", record, "--out", workspace / "ready.pdf", ok=False)
    cv = report["adapted_cv"]
    cv["summary"] = CANDIDATE["cv"]["summary"]
    cv_path = save(workspace / "edited.json", cv)
    revised = run_cli(workspace, "revise", "--record", record, "--cv", cv_path)
    assert revised["record_id"] != record
    assert "stale" in run_cli(workspace, "confirm", "--record", revised["record_id"], "--review", review_path, ok=False)
    history = run_cli(workspace, "history")
    assert history[0]["parent_id"] == record


def test_submission_ledger_blocks_duplicates_and_uncertain_retries(workspace):
    generated = generate_fixture(workspace, changed=False)
    record = generated["record_id"]
    job = save(workspace / "job.json", {"source_url": "https://www.linkedin.com/jobs/view/123?trk=search",
               "title": "Python Developer", "company": "Example", "description": "Python developer for Example"})
    for state in ("discovered", "shortlisted", "cv_ready", "prepared", "submitting", "uncertain"):
        run_cli(workspace, "track", "--job", job, "--state", state, "--record", record)
    assert "uncertain" in run_cli(workspace, "track", "--job", job, "--state", "prepared", ok=False)
    assert "requires --evidence" in run_cli(workspace, "track", "--job", job, "--state", "submitted", ok=False)
    evidence = save(workspace / "receipt.json", {"confirmation_text": "Application received", "observed_at": "2026-10-05T12:00:00-05:00", "destination_url": "https://example.com/received"})
    entry = run_cli(workspace, "track", "--job", job, "--state", "submitted", "--evidence", evidence)
    assert entry["record_id"] == record
    assert "duplicate" in run_cli(workspace, "track", "--job", job, "--state", "discovered", ok=False)
    assert len(run_cli(workspace, "applications")) == 1


def test_ledger_requires_correct_job_and_valid_transitions(workspace):
    generated = generate_fixture(workspace, changed=False)
    job = save(workspace / "job.json", {"source_url": "https://example.com/jobs/1", "title": "Python Developer",
               "company": "Example", "description": "A different vacancy"})
    assert "Invalid transition" in run_cli(workspace, "track", "--job", job, "--state", "submitted", ok=False)
    run_cli(workspace, "track", "--job", job, "--state", "discovered")
    run_cli(workspace, "track", "--job", job, "--state", "shortlisted")
    assert "different job" in run_cli(workspace, "track", "--job", job, "--state", "cv_ready", "--record", generated["record_id"], ok=False)


def test_job_url_canonicalization():
    assert canonical_url("https://co.linkedin.com/jobs/view/developer-123?trk=search") == "https://www.linkedin.com/jobs/view/123"
    assert canonical_url("https://www.linkedin.com/jobs/search/?currentJobId=123") == "https://www.linkedin.com/jobs/view/123"
    assert canonical_url("https://ats.example/jobs?id=2&utm_source=linkedin") == "https://ats.example/jobs?id=2"
    with pytest.raises(ValueError):
        canonical_url("https://user:password@example.com/jobs/2")


def test_export_validates_the_actual_download_not_just_saved_copy(workspace):
    generated = generate_fixture(workspace, changed=False)
    (workspace / "generated" / generated["pdf_filename"]).write_bytes(b"corrupt")
    report = run_cli(workspace, "inspect", "--record", generated["record_id"])
    assert report["quality"]["pdf_valid"]  # saved/ is still intact
    run_cli(workspace, "export", "--record", generated["record_id"], "--out", workspace / "wrong.pdf", ok=False)
    assert not (workspace / "wrong.pdf").exists()


def test_portable_bundle_runs_without_personal_seed(tmp_path):
    import zipfile
    from scripts.package_application_assistant import build
    result = build(tmp_path / "delivery")
    with zipfile.ZipFile(result["archive"]) as bundle:
        names = bundle.namelist()
        assert "generator/app/cli.py" in names
        assert "generator/app/data/base_cv.py" not in names
        assert not any(name.endswith(".env") or "history.json" in name for name in names)
        bundle.extractall(tmp_path / "unpacked")
    candidate = save(tmp_path / "candidate.json", CANDIDATE)
    result = subprocess.run([sys.executable, "-m", "app.cli", "--workspace", str(tmp_path / "portable-workspace"),
                             "init", "--candidate", str(candidate)], cwd=tmp_path / "unpacked" / "generator",
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["initialized"]
    generated = generate_fixture(tmp_path / "portable-workspace", changed=False,
                                 repo=tmp_path / "unpacked" / "generator")
    assert generated["adapted_cv"]["contact"]["name"] == "Ana Example"
    assert (tmp_path / "portable-workspace" / "saved" / generated["pdf_filename"]).is_file()

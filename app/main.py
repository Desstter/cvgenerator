import os
# Disable runtime telemetry before importing PDF/ONNX dependencies.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

import shutil
import re
import time
import traceback
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.schemas import (CVData, JobDescription, AdaptationResult, BaseCVStore,
                                ClaimConfirmation, ApplicationFeedback)
from app.services.pdf_parser import extract_as_markdown
from app.services.cv_analyzer import (analyze_cv_rule_based, is_parse_sufficient,
                                      validate_cv_data, critical_cv_errors)
from app.services.ai_adapter import get_provider, parse_cv_with_ai, analyze_and_adapt, refine_cv
from app.services.history import (load_history, load_application, save_application,
                                  confirm_application, update_application_feedback,
                                  delete_application)
from app.services.base_cv_store import (
    load_base_cv,
    save_base_cv,
    build_real_context,
    get_profile_definition,
    list_profile_definitions,
)
from app.services.ats_optimizer import analyze_keyword_match, reorder_skills
from app.services.cv_compactor import compact_one_bullet
from app.services.cv_quality import editorial_issues, evidence_questions
from app.services.pdf_generator import ALLOWED_TEMPLATES, generate_pdf_from_template
from app.services.claim_guard import sanitize_adaptation, review_claims
from app.services.opportunity_store import list_opportunities
from app.services.event_log import log_event, get_events, clear_events, install_logging_bridge, Timer

logging.basicConfig(level=logging.INFO)
install_logging_bridge()
logger = logging.getLogger(__name__)


def _error_detail(e: Exception, context: str) -> dict:
    """Full error payload for the frontend: message + traceback (personal app,
    everything is shown on screen)."""
    tb = traceback.format_exc()
    log_event(context, f"{type(e).__name__}: {e}", level="error", detail=tb)
    return {"message": f"{type(e).__name__}: {e}", "traceback": tb}


def _profile_or_400(profile_id: str):
    try:
        return get_profile_definition(profile_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

app = FastAPI(title="CV Generator", version="4.0.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# First event on every boot: if the Activity Log shows nothing at page load,
# the running server process predates the event-log feature.
log_event(
    "server",
    f"Backend ready (v{app.version}) — provider={settings.ai_provider}, "
    f"refine_pass={'on' if settings.refine_pass else 'off'}, event log active",
    level="success",
)


def _cleanup_old_outputs():
    """Remove output PDFs older than 1 hour."""
    cutoff = time.time() - 3600
    for f in settings.outputs_dir.glob("*.pdf"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        except OSError:
            pass


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/api/events")
async def api_events(since: int = 0):
    """Live activity feed: every API call, retry, fallback and error with traceback."""
    return get_events(since)


@app.delete("/api/events")
async def api_events_clear():
    clear_events()
    return {"ok": True}


@app.post("/api/analyze")
def analyze_cv(file: UploadFile = File(...)):
    """Upload a PDF and get the parsed CV structure back.

    Sync endpoint on purpose: FastAPI runs it in a threadpool so the blocking
    AI/PDF work doesn't stall the event loop.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    content = file.file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

    pdf_path = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    pdf_path.write_bytes(content)

    try:
        with Timer("parse", f"Extracting text from {file.filename}"):
            markdown = extract_as_markdown(pdf_path)
        cv = analyze_cv_rule_based(markdown)

        if not is_parse_sufficient(cv):
            logger.info("Rule-based parsing insufficient, using AI fallback")
            provider = get_provider()
            cv = parse_cv_with_ai(provider, markdown)

        warnings = validate_cv_data(cv)
        return {"cv": cv.model_dump(exclude={"raw_markdown"}),
                "warnings": warnings, "critical_errors": critical_cv_errors(cv)}
    except Exception as e:
        raise HTTPException(500, _error_detail(e, "analyze"))
    finally:
        pdf_path.unlink(missing_ok=True)


@app.post("/api/adapt")
def adapt_cv_endpoint(
    job_description: str = Form(...),
    file: Optional[UploadFile] = File(None),
    template: str = Form("modern"),
    provider_name: str = Form(""),
    profile_id: str = Form("developer"),
    confirmed_cv_json: str = Form(""),
):
    """Adapt CV to job description. PDF upload is optional — uses base CV if not provided.

    Sync endpoint on purpose: FastAPI runs it in a threadpool so the long blocking
    AI calls don't stall the event loop for other requests.
    """
    if not job_description.strip():
        raise HTTPException(400, "Job description is empty")
    if template not in ALLOWED_TEMPLATES:
        raise HTTPException(400, "Choose a supported PDF template")
    _cleanup_old_outputs()
    real_context = ""
    started = time.perf_counter()
    log_event(
        "pipeline",
        f"━━ New adaptation request (profile={profile_id}, template={template}, "
        f"provider={provider_name or settings.ai_provider}, "
        f"job description: {len(job_description):,} chars) ━━",
    )

    try:
        profile = _profile_or_400(profile_id)
        profile_type = profile.profile_type
        store = load_base_cv(profile_id)
        if confirmed_cv_json:
            try:
                cv = CVData.model_validate_json(confirmed_cv_json)
            except ValueError as exc:
                raise HTTPException(400, f"Confirmed CV is invalid: {exc}") from exc
            critical = critical_cv_errors(cv)
            if critical:
                raise HTTPException(400, {"message": "Imported CV is incomplete", "errors": critical})
            warnings = validate_cv_data(cv)
            if warnings:
                log_event("parse", "Confirmed imported CV warnings: " + "; ".join(warnings), level="warn")
            provider = get_provider(provider_name or None)
        elif file and file.filename:
            raise HTTPException(400, {
                "message": "Review and confirm the imported CV with /api/analyze before adapting it.",
            })
        else:
            # No PDF — use the editable base CV
            logger.info("Using %s base CV (no PDF uploaded)", profile_id)
            cv = store.cv
            critical = critical_cv_errors(cv)
            if critical:
                raise HTTPException(400, {"message": "Base CV is incomplete", "errors": critical})
            real_context = build_real_context(store)
            provider = get_provider(provider_name or None)

        # Analyze job and adapt CV in a single API call
        with Timer("ai", "Analyzing job & adapting CV (AI pass 1/2)"):
            job, adapted_cv = analyze_and_adapt(
                provider,
                cv,
                job_description,
                real_context=real_context,
                profile_type=profile_type,
            )
        log_event(
            "ai",
            f"Job detected: \"{job.title}\"{' at ' + job.company if job.company else ''} "
            f"[{job.detected_language}] — {len(job.required_skills)} required / "
            f"{len(job.preferred_skills)} preferred skills",
        )
        first_pass_cv = adapted_cv.model_copy(deep=True)
        first_pass_model = getattr(provider, "model", "")

        # Second pass: recruiter-style critique that rewrites weak bullets/summary
        if settings.refine_pass:
            with Timer("ai", "Recruiter critique & rewrite (AI pass 2/2)"):
                adapted_cv = refine_cv(
                    provider, adapted_cv, job, profile_type=profile_type,
                    source_cv=cv, real_context=real_context,
                )
        else:
            log_event("ai", "Refine pass disabled in config — skipping AI pass 2/2")

        adapted_cv = sanitize_adaptation(cv, adapted_cv, profile_type=profile_type)
        claim_review = review_claims(cv, adapted_cv, real_context, profile_type=profile_type)
        if claim_review.status == "blocked":
            raise ValueError(
                "Truth review blocked the generated CV: "
                + "; ".join(claim_review.unsupported_claims)
            )
        log_event(
            "claims",
            f"Truth review: {claim_review.status}; {len(claim_review.review_items)} rewritten claims to inspect",
            level="success" if claim_review.status == "passed" else "warn",
        )

        # Technology substitution is intentionally disabled. Relevance comes from
        # ordering and evidence, not relabelling one stack as another.
        tech_swaps = []

        # ATS optimization — score BEFORE adaptation (baseline) and AFTER (final)
        all_job_keywords = job.required_skills + job.preferred_skills + job.keywords
        # Only curated, code-owned equivalences count toward coverage.
        original_ats_score = analyze_keyword_match(cv, job, profile_type=profile_type)
        adapted_cv.skills = reorder_skills(
            adapted_cv.skills,
            all_job_keywords,
            profile_type=profile_type,
        )
        ats_score = analyze_keyword_match(adapted_cv, job, profile_type=profile_type)
        log_event(
            "ats",
            f"Keyword coverage: {original_ats_score.overall_score:.0f}% → {ats_score.overall_score:.0f}% "
            f"({len(ats_score.matched_keywords)} matched, {len(ats_score.missing_keywords)} missing)",
            level="success",
        )
        if tech_swaps:
            log_event("ats", f"Tech substitutions: {', '.join(tech_swaps)}")

        # Build job analysis summary
        job_analysis = {
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills,
            "detected_language": job.detected_language,
        }

        # BPO output is deliberately locked to the verified one-page template.
        if profile.one_page_required:
            template = profile.default_template

        # Generate PDF
        with Timer("pdf", f"Generating PDF (template={template})"):
            if template == "original":
                raise HTTPException(400, "Original PDF editing is unavailable because it can truncate text. Choose a template.")
            for attempt in range(8):
                try:
                    output_path = generate_pdf_from_template(
                        adapted_cv,
                        matched_keywords=ats_score.matched_keywords,
                        template_name=template,
                        job_title=job.title,
                        max_pages=profile.max_pages,
                    )
                    break
                except ValueError as exc:
                    if "requires at most" not in str(exc) or not compact_one_bullet(adapted_cv, job):
                        raise
                    log_event("pdf", "Page overflow: removed the least relevant bullet and retrying", level="warn")
                    claim_review = review_claims(cv, adapted_cv, real_context, profile_type=profile_type)
                    ats_score = analyze_keyword_match(adapted_cv, job, profile_type=profile_type)
            else:
                raise ValueError("Could not fit the verified CV within the page limit")

        # Persist PDF to saved/ so it survives the 1-hour outputs/ cleanup
        saved_pdf = settings.saved_dir / output_path.name
        if output_path.resolve() != saved_pdf.resolve():
            shutil.copy2(output_path, saved_pdf)
        quality_issues = editorial_issues(adapted_cv)

        # Save to application history
        record = save_application(
            job_title=job.title,
            company=job.company,
            ats_score=ats_score.overall_score,
            required_score=ats_score.required_score,
            preferred_score=ats_score.preferred_score,
            pdf_filename=output_path.name,
            detected_language=job.detected_language,
            profile_id=profile_id,
            reviewed=claim_review.status == "passed",
            snapshot={
                "source_cv": cv.model_dump(exclude={"raw_markdown"}),
                "adapted_cv": adapted_cv.model_dump(exclude={"raw_markdown"}),
                "ai_first_pass_cv": first_pass_cv.model_dump(exclude={"raw_markdown"}),
                "job_description": job_description,
                "job_analysis": job.model_dump(),
                "real_context": real_context,
                "provider": provider_name or settings.ai_provider,
                "model": getattr(provider, "model", ""),
                "first_pass_model": first_pass_model,
                "refine_pass": settings.refine_pass,
                "template": template,
                "claim_review": claim_review.model_dump(),
                "coverage_before": original_ats_score.model_dump(),
                "coverage_after": ats_score.model_dump(),
                "quality_issues": quality_issues,
                "evidence_questions": evidence_questions(ats_score),
            },
        )

        result = AdaptationResult(
            original_cv=cv,
            adapted_cv=adapted_cv,
            ats_score=ats_score,
            original_ats_score=original_ats_score,
            pdf_filename=output_path.name,
            tech_swaps=tech_swaps,
            job_analysis=job_analysis,
            profile_id=profile_id,
            claim_review=claim_review,
            record_id=record["id"],
            quality_issues=quality_issues,
            evidence_questions=evidence_questions(ats_score),
        )

        log_event(
            "pipeline",
            f"━━ Done in {time.perf_counter() - started:.1f}s → {output_path.name} ━━",
            level="success",
        )
        return result.model_dump(exclude={"original_cv": {"raw_markdown"}, "adapted_cv": {"raw_markdown"}})

    except HTTPException:
        raise
    except Exception as e:
        detail = _error_detail(e, "pipeline")
        err_msg = str(e).lower()
        if re.search(r"\b(?:quota|429)\b|\brate[\s_-]*limit", err_msg):
            detail["message"] = (
                "AI provider rate limit exceeded. Wait a minute and try again, "
                f"or switch provider. ({detail['message']})"
            )
            raise HTTPException(429, detail)
        raise HTTPException(500, detail)


@app.get("/api/profiles")
async def get_profiles():
    return [profile.model_dump() for profile in list_profile_definitions()]


@app.get("/api/opportunities")
async def get_opportunities(profile: str = ""):
    """Return the curated real-job catalog, optionally filtered by CV profile."""
    if profile:
        _profile_or_400(profile)
    return [item.model_dump() for item in list_opportunities(profile or None)]


@app.get("/api/base-cv")
def base_cv_pdf(profile: str = "developer", template: str = ""):
    """Generate and download the base CV with real technologies, no adaptation."""
    definition = _profile_or_400(profile)
    cv = load_base_cv(profile).cv
    selected_template = definition.default_template if definition.one_page_required else (template or definition.default_template)
    title = "Bilingual_Customer_Service" if definition.profile_type == "bpo" else ""
    output_path = generate_pdf_from_template(
        cv,
        matched_keywords=[],
        template_name=selected_template,
        job_title=title,
        max_pages=definition.max_pages,
    )
    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename=output_path.name,
    )


@app.get("/api/base-cv-data")
async def get_base_cv_data(profile: str = "developer"):
    """Return the editable base CV store (CV data + hidden real context)."""
    _profile_or_400(profile)
    return load_base_cv(profile).model_dump(exclude={"cv": {"raw_markdown"}})


@app.put("/api/base-cv-data")
async def update_base_cv_data(store: BaseCVStore, profile: str = "developer"):
    """Persist edits to the base CV store."""
    _profile_or_400(profile)
    critical = critical_cv_errors(store.cv)
    if critical:
        raise HTTPException(400, {"message": "Base CV is incomplete", "errors": critical})
    try:
        saved = save_base_cv(store, profile)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return saved.model_dump(exclude={"cv": {"raw_markdown"}})


@app.get("/api/download/{filename}")
async def download_pdf(filename: str):
    """Download a generated PDF — checks outputs/ first, then saved/ for history downloads."""
    safe_name = Path(filename).name
    file_path = settings.outputs_dir / safe_name
    if not file_path.exists():
        file_path = settings.saved_dir / safe_name
    if not file_path.exists():
        raise HTTPException(404, "File not found or expired")
    record = next((item for item in load_history() if item.get("pdf_filename") == safe_name), None)
    if record and not record.get("reviewed", True):
        raise HTTPException(409, "Review and confirm the generated claims before downloading")
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=safe_name,
    )


@app.get("/api/history")
async def get_history():
    return [{key: value for key, value in record.items() if key != "snapshot"}
            for record in load_history()]


@app.get("/api/history/{record_id}")
async def get_history_entry(record_id: str):
    record = load_application(record_id)
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


@app.post("/api/history/{record_id}/confirm")
async def confirm_history_entry(record_id: str, confirmation: ClaimConfirmation):
    record = load_application(record_id)
    if record is None:
        raise HTTPException(404, "Record not found")
    review = record.get("snapshot", {}).get("claim_review", {})
    if review.get("status") == "blocked":
        raise HTTPException(422, "Unsupported claims must be corrected before download")
    expected = {item["field"] for item in review.get("review_items", [])}
    if expected - set(confirmation.fields):
        raise HTTPException(422, "Confirm each rewritten claim before downloading")
    confirm_application(record_id)
    return {"ok": True}


@app.put("/api/history/{record_id}/feedback")
async def save_history_feedback(record_id: str, feedback: ApplicationFeedback):
    if not update_application_feedback(record_id, feedback.outcome, feedback.notes):
        raise HTTPException(404, "Record not found")
    return {"ok": True}


@app.post("/api/history/{record_id}/revise")
def revise_history_entry(record_id: str, edited_cv: CVData):
    """Re-render human edits without another AI call, preserving the source snapshot."""
    record = load_application(record_id)
    if not record or not record.get("snapshot"):
        raise HTTPException(404, "Editable application snapshot not found")
    snapshot = record["snapshot"]
    source = CVData.model_validate(snapshot["source_cv"])
    verified_skills = {skill.casefold() for skill in source.skills}
    unknown_skills = [skill for skill in edited_cv.skills if skill.casefold() not in verified_skills]
    if unknown_skills:
        raise HTTPException(422, "Add new skills to the verified master CV first: " + ", ".join(unknown_skills))
    job = JobDescription.model_validate(snapshot["job_analysis"])
    profile = _profile_or_400(record["profile_id"])
    adapted = sanitize_adaptation(source, edited_cv, profile.profile_type)
    review = review_claims(source, adapted, snapshot.get("real_context", ""), profile.profile_type)
    if review.status == "blocked":
        raise HTTPException(422, {"message": "Edited CV contains unsupported claims", "review": review.model_dump()})
    score_before = analyze_keyword_match(source, job, profile_type=profile.profile_type)
    score_after = analyze_keyword_match(adapted, job, profile_type=profile.profile_type)
    template = snapshot.get("template") or profile.default_template
    if profile.one_page_required:
        template = profile.default_template
    try:
        output = generate_pdf_from_template(
            adapted, matched_keywords=score_after.matched_keywords,
            template_name=template, job_title=job.title, max_pages=profile.max_pages,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    saved_pdf = settings.saved_dir / output.name
    if output.resolve() != saved_pdf.resolve():
        shutil.copy2(output, saved_pdf)
    updated_snapshot = dict(snapshot)
    updated_snapshot.update({
        "adapted_cv": adapted.model_dump(exclude={"raw_markdown"}),
        "claim_review": review.model_dump(),
        "coverage_after": score_after.model_dump(),
        "quality_issues": editorial_issues(adapted),
        "evidence_questions": evidence_questions(score_after),
    })
    new_record = save_application(
        job_title=job.title, company=job.company, ats_score=score_after.overall_score,
        required_score=score_after.required_score, preferred_score=score_after.preferred_score,
        pdf_filename=output.name, detected_language=job.detected_language,
        profile_id=record["profile_id"], snapshot=updated_snapshot,
        reviewed=review.status == "passed", parent_id=record_id,
    )
    return AdaptationResult(
        original_cv=source, adapted_cv=adapted, ats_score=score_after,
        original_ats_score=score_before, pdf_filename=output.name,
        job_analysis={"title": job.title, "company": job.company,
                      "required_skills": job.required_skills,
                      "preferred_skills": job.preferred_skills,
                      "detected_language": job.detected_language},
        profile_id=record["profile_id"], claim_review=review,
        record_id=new_record["id"],
        quality_issues=updated_snapshot["quality_issues"],
        evidence_questions=updated_snapshot["evidence_questions"],
    ).model_dump(exclude={"original_cv": {"raw_markdown"}, "adapted_cv": {"raw_markdown"}})


@app.delete("/api/history/{record_id}")
async def delete_history_entry(record_id: str):
    deleted = delete_application(record_id)
    if not deleted:
        raise HTTPException(404, "Record not found")
    return {"ok": True}

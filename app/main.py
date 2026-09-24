import shutil
import time
import traceback
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.models.schemas import CVData, AdaptationResult, BaseCVStore, ClaimReview
from app.services.pdf_parser import extract_as_markdown
from app.services.cv_analyzer import analyze_cv_rule_based, is_parse_sufficient, validate_cv_data
from app.services.ai_adapter import get_provider, parse_cv_with_ai, analyze_and_adapt, refine_cv
from app.services.history import load_history, save_application, delete_application
from app.services.base_cv_store import (
    load_base_cv,
    save_base_cv,
    build_real_context,
    get_profile_definition,
    list_profile_definitions,
)
from app.services.ats_optimizer import analyze_keyword_match, reorder_skills
from app.services.pdf_generator import generate_pdf_from_template, generate_pdf_inplace
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

        validate_cv_data(cv)
        return cv.model_dump(exclude={"raw_markdown"})
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
):
    """Adapt CV to job description. PDF upload is optional — uses base CV if not provided.

    Sync endpoint on purpose: FastAPI runs it in a threadpool so the long blocking
    AI calls don't stall the event loop for other requests.
    """
    _cleanup_old_outputs()
    pdf_path = None
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
        if file and file.filename:
            # Custom PDF uploaded — use old flow
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(400, "Only PDF files are accepted")

            content = file.file.read()
            if len(content) > settings.max_upload_size_mb * 1024 * 1024:
                raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

            pdf_path = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
            pdf_path.write_bytes(content)

            with Timer("parse", f"Parsing uploaded CV ({file.filename})"):
                markdown = extract_as_markdown(pdf_path)
                cv = analyze_cv_rule_based(markdown)
            provider = get_provider(provider_name or None)

            if not is_parse_sufficient(cv):
                logger.info("Rule-based parsing insufficient, using AI fallback")
                cv = parse_cv_with_ai(provider, markdown)

            validate_cv_data(cv)
        else:
            # No PDF — use the editable base CV
            logger.info("Using %s base CV (no PDF uploaded)", profile_id)
            cv = store.cv
            real_context = build_real_context(store)
            provider = get_provider(provider_name or None)

        # Analyze job and adapt CV in a single API call
        with Timer("ai", "Analyzing job & adapting CV (AI pass 1/2)"):
            job, adapted_cv, equivalences = analyze_and_adapt(
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
            f"{len(job.preferred_skills)} preferred skills, "
            f"{len(equivalences)} keyword equivalences",
        )

        # Second pass: recruiter-style critique that rewrites weak bullets/summary
        if settings.refine_pass:
            with Timer("ai", "Recruiter critique & rewrite (AI pass 2/2)"):
                adapted_cv = refine_cv(provider, adapted_cv, job, profile_type=profile_type)
        else:
            log_event("ai", "Refine pass disabled in config — skipping AI pass 2/2")

        adapted_cv = sanitize_adaptation(cv, adapted_cv, profile_type=profile_type)
        claim_review = review_claims(cv, adapted_cv, real_context, profile_type=profile_type)
        if claim_review.status != "passed":
            raise ValueError(
                "Truth review blocked the generated CV: "
                + "; ".join(claim_review.unsupported_claims)
            )
        log_event(
            "claims",
            "Truth review passed — protected fields and verified skills preserved",
            level="success",
        )

        # Technology substitution is intentionally disabled. Relevance comes from
        # ordering and evidence, not relabelling one stack as another.
        tech_swaps = []

        # ATS optimization — score BEFORE adaptation (baseline) and AFTER (final)
        all_job_keywords = job.required_skills + job.preferred_skills + job.keywords
        original_ats_score = analyze_keyword_match(
            cv, job, extra_synonyms=equivalences, profile_type=profile_type
        )
        adapted_cv.skills = reorder_skills(
            adapted_cv.skills,
            all_job_keywords,
            extra_synonyms=equivalences,
            profile_type=profile_type,
        )
        ats_score = analyze_keyword_match(
            adapted_cv, job, extra_synonyms=equivalences, profile_type=profile_type
        )
        log_event(
            "ats",
            f"ATS score: {original_ats_score.overall_score:.0f}% → {ats_score.overall_score:.0f}% "
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
            if template == "original" and pdf_path:
                output_path = generate_pdf_inplace(pdf_path, cv, adapted_cv)
            else:
                output_path = generate_pdf_from_template(
                    adapted_cv,
                    matched_keywords=ats_score.matched_keywords,
                    template_name=template,
                    job_title=job.title,
                    max_pages=profile.max_pages,
                )

        # Persist PDF to saved/ so it survives the 1-hour outputs/ cleanup
        saved_pdf = settings.saved_dir / output_path.name
        shutil.copy2(output_path, saved_pdf)

        # Save to application history
        save_application(
            job_title=job.title,
            company=job.company,
            ats_score=ats_score.overall_score,
            required_score=ats_score.required_score,
            preferred_score=ats_score.preferred_score,
            pdf_filename=output_path.name,
            detected_language=job.detected_language,
            profile_id=profile_id,
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
        if "quota" in err_msg or "rate" in err_msg or "429" in err_msg:
            detail["message"] = (
                "AI provider rate limit exceeded. Wait a minute and try again, "
                f"or switch provider. ({detail['message']})"
            )
            raise HTTPException(429, detail)
        raise HTTPException(500, detail)
    finally:
        if pdf_path:
            pdf_path.unlink(missing_ok=True)


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
        max_pages=1 if definition.one_page_required else None,
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
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=safe_name,
    )


@app.get("/api/history")
async def get_history():
    return load_history()


@app.delete("/api/history/{record_id}")
async def delete_history_entry(record_id: str):
    deleted = delete_application(record_id)
    if not deleted:
        raise HTTPException(404, "Record not found")
    return {"ok": True}

import json
import shutil
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.models.schemas import CVData, AdaptationResult, BaseCVStore
from app.services.pdf_parser import extract_as_markdown
from app.services.cv_analyzer import analyze_cv_rule_based, is_parse_sufficient, validate_cv_data
from app.services.ai_adapter import get_provider, analyze_job, adapt_cv, parse_cv_with_ai, analyze_and_adapt
from app.services.history import load_history, save_application, delete_application
from app.services.base_cv_store import load_base_cv, save_base_cv, build_real_context
from app.services.ats_optimizer import analyze_keyword_match, reorder_skills
from app.services.pdf_generator import generate_pdf_from_template, generate_pdf_inplace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CV Generator", version="2.0.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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


@app.post("/api/analyze")
async def analyze_cv(file: UploadFile = File(...)):
    """Upload a PDF and get the parsed CV structure back."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

    pdf_path = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    pdf_path.write_bytes(content)

    try:
        markdown = extract_as_markdown(pdf_path)
        cv = analyze_cv_rule_based(markdown)

        if not is_parse_sufficient(cv):
            logger.info("Rule-based parsing insufficient, using AI fallback")
            provider = get_provider()
            cv = parse_cv_with_ai(provider, markdown)

        validate_cv_data(cv)
        return cv.model_dump(exclude={"raw_markdown"})
    except Exception as e:
        logger.exception("Error analyzing CV")
        raise HTTPException(500, f"Error analyzing CV: {str(e)}")
    finally:
        pdf_path.unlink(missing_ok=True)


@app.post("/api/adapt")
async def adapt_cv_endpoint(
    job_description: str = Form(...),
    file: Optional[UploadFile] = File(None),
    template: str = Form("modern"),
    provider_name: str = Form(""),
):
    """Adapt CV to job description. PDF upload is optional — uses base CV if not provided."""
    _cleanup_old_outputs()
    pdf_path = None
    real_context = ""

    try:
        if file and file.filename:
            # Custom PDF uploaded — use old flow
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(400, "Only PDF files are accepted")

            content = await file.read()
            if len(content) > settings.max_upload_size_mb * 1024 * 1024:
                raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

            pdf_path = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
            pdf_path.write_bytes(content)

            markdown = extract_as_markdown(pdf_path)
            cv = analyze_cv_rule_based(markdown)
            provider = get_provider(provider_name or None)

            if not is_parse_sufficient(cv):
                logger.info("Rule-based parsing insufficient, using AI fallback")
                cv = parse_cv_with_ai(provider, markdown)

            validate_cv_data(cv)
        else:
            # No PDF — use the editable base CV
            logger.info("Using base CV (no PDF uploaded)")
            store = load_base_cv()
            cv = store.cv
            real_context = build_real_context(store)
            provider = get_provider(provider_name or None)

        # Analyze job and adapt CV in a single API call
        job, adapted_cv = analyze_and_adapt(provider, cv, job_description, real_context=real_context)

        # Detect technology substitutions
        tech_swaps = []
        for orig_exp, new_exp in zip(cv.experience, adapted_cv.experience):
            orig_set = {t.lower() for t in orig_exp.technologies}
            new_set = {t.lower() for t in new_exp.technologies}
            removed = [t for t in orig_exp.technologies if t.lower() not in new_set]
            added = [t for t in new_exp.technologies if t.lower() not in orig_set]
            for old_t, new_t in zip(removed, added):
                tech_swaps.append(f"{old_t} → {new_t}")

        # ATS optimization
        all_job_keywords = job.required_skills + job.preferred_skills + job.keywords
        adapted_cv.skills = reorder_skills(adapted_cv.skills, all_job_keywords)
        ats_score = analyze_keyword_match(adapted_cv, job)

        # Build job analysis summary
        job_analysis = {
            "title": job.title,
            "company": job.company,
            "required_skills": job.required_skills,
            "preferred_skills": job.preferred_skills,
            "detected_language": job.detected_language,
        }

        # Generate PDF
        if template == "original" and pdf_path:
            output_path = generate_pdf_inplace(pdf_path, cv, adapted_cv)
        else:
            output_path = generate_pdf_from_template(
                adapted_cv,
                matched_keywords=ats_score.matched_keywords,
                template_name=template,
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
        )

        result = AdaptationResult(
            original_cv=cv,
            adapted_cv=adapted_cv,
            ats_score=ats_score,
            pdf_filename=output_path.name,
            tech_swaps=tech_swaps,
            job_analysis=job_analysis,
        )

        return result.model_dump(exclude={"original_cv": {"raw_markdown"}, "adapted_cv": {"raw_markdown"}})

    except Exception as e:
        logger.exception("Error adapting CV")
        err_msg = str(e).lower()
        if "quota" in err_msg or "rate" in err_msg or "429" in err_msg:
            raise HTTPException(429, "AI provider rate limit exceeded. Wait a minute and try again, or switch to a different provider.")
        raise HTTPException(500, f"Error adapting CV: {str(e)}")
    finally:
        if pdf_path:
            pdf_path.unlink(missing_ok=True)


@app.get("/api/base-cv")
async def base_cv_pdf(template: str = "modern"):
    """Generate and download the base CV with real technologies, no adaptation."""
    cv = load_base_cv().cv
    output_path = generate_pdf_from_template(cv, matched_keywords=[], template_name=template)
    return FileResponse(
        str(output_path),
        media_type="application/pdf",
        filename="CV_Santiago_Hurtado_Base.pdf",
    )


@app.get("/api/base-cv-data")
async def get_base_cv_data():
    """Return the editable base CV store (CV data + hidden real context)."""
    return load_base_cv().model_dump(exclude={"cv": {"raw_markdown"}})


@app.put("/api/base-cv-data")
async def update_base_cv_data(store: BaseCVStore):
    """Persist edits to the base CV store."""
    saved = save_base_cv(store)
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

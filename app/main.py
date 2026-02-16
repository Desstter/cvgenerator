import uuid
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.models.schemas import CVData, AdaptationResult
from app.services.pdf_parser import extract_as_markdown
from app.services.cv_analyzer import analyze_cv_rule_based, is_parse_sufficient, validate_cv_data
from app.services.ai_adapter import get_provider, analyze_job, adapt_cv, parse_cv_with_ai
from app.services.ats_optimizer import analyze_keyword_match, reorder_skills
from app.services.pdf_generator import generate_pdf_from_template, generate_pdf_inplace

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CV Generator", version="1.0.0")

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


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

        # Validate parsed CV data
        validate_cv_data(cv)

        return cv.model_dump(exclude={"raw_markdown"})
    except Exception as e:
        logger.exception("Error analyzing CV")
        raise HTTPException(500, f"Error analyzing CV: {str(e)}")
    finally:
        pdf_path.unlink(missing_ok=True)


@app.post("/api/adapt")
async def adapt_cv_endpoint(
    file: UploadFile = File(...),
    job_description: str = Form(...),
    template: str = Form("modern"),
    provider_name: str = Form(""),
):
    """Upload PDF + job description, get adapted PDF + ATS score."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {settings.max_upload_size_mb}MB)")

    pdf_path = settings.uploads_dir / f"{uuid.uuid4().hex}.pdf"
    pdf_path.write_bytes(content)

    try:
        # Step 1: Parse PDF
        markdown = extract_as_markdown(pdf_path)

        # Step 2: Analyze CV structure
        cv = analyze_cv_rule_based(markdown)
        provider = get_provider(provider_name or None)

        if not is_parse_sufficient(cv):
            logger.info("Rule-based parsing insufficient, using AI fallback")
            cv = parse_cv_with_ai(provider, markdown)

        # Validate parsed CV data
        validate_cv_data(cv)

        # Step 3: Analyze job description
        job = analyze_job(provider, job_description)

        # Step 4: Adapt CV with AI
        adapted_cv = adapt_cv(provider, cv, job)

        # Step 5: ATS optimization
        all_job_keywords = job.required_skills + job.preferred_skills + job.keywords
        adapted_cv.skills = reorder_skills(adapted_cv.skills, all_job_keywords)
        ats_score = analyze_keyword_match(adapted_cv, job)

        # Step 6: Generate PDF
        if template == "original":
            output_path = generate_pdf_inplace(pdf_path, cv, adapted_cv)
        else:
            output_path = generate_pdf_from_template(
                adapted_cv,
                matched_keywords=ats_score.matched_keywords,
                template_name=template,
            )

        result = AdaptationResult(
            original_cv=cv,
            adapted_cv=adapted_cv,
            ats_score=ats_score,
            pdf_filename=output_path.name,
        )

        return result.model_dump(exclude={"original_cv": {"raw_markdown"}, "adapted_cv": {"raw_markdown"}})

    except Exception as e:
        logger.exception("Error adapting CV")
        raise HTTPException(500, f"Error adapting CV: {str(e)}")
    finally:
        pdf_path.unlink(missing_ok=True)


@app.get("/api/download/{filename}")
async def download_pdf(filename: str):
    """Download a generated PDF."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    file_path = settings.outputs_dir / safe_name
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(
        str(file_path),
        media_type="application/pdf",
        filename=safe_name,
    )

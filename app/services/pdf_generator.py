import uuid
import fitz
from io import BytesIO
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.config import settings
from app.models.schemas import CVData


def generate_pdf_from_template(
    cv: CVData,
    matched_keywords: list[str] | None = None,
    template_name: str = "modern",
) -> Path:
    """Generate a PDF from an HTML template using xhtml2pdf."""
    env = Environment(loader=FileSystemLoader(str(settings.templates_dir)))
    template = env.get_template(f"{template_name}.html")

    html_content = template.render(
        cv=cv,
        matched_keywords=matched_keywords or [],
    )

    output_filename = f"cv_{uuid.uuid4().hex[:8]}.pdf"
    output_path = settings.outputs_dir / output_filename

    with open(str(output_path), "wb") as f:
        pisa_status = pisa.CreatePDF(html_content, dest=f)
        if pisa_status.err:
            raise RuntimeError(f"PDF generation failed with {pisa_status.err} errors")

    return output_path


def generate_pdf_inplace(
    original_pdf_path: str | Path,
    original_cv: CVData,
    adapted_cv: CVData,
) -> Path:
    """Attempt in-place PDF editing using PyMuPDF redaction.

    Replaces text blocks in the original PDF while preserving layout.
    Falls back to template generation if in-place editing fails.
    """
    try:
        doc = fitz.open(str(original_pdf_path))
        _apply_text_replacements(doc, original_cv, adapted_cv)

        output_filename = f"cv_inplace_{uuid.uuid4().hex[:8]}.pdf"
        output_path = settings.outputs_dir / output_filename
        doc.save(str(output_path))
        doc.close()
        return output_path
    except Exception:
        # Fallback to template-based generation
        return generate_pdf_from_template(adapted_cv)


def _apply_text_replacements(doc: fitz.Document, original: CVData, adapted: CVData):
    """Replace text in PDF using redaction annotations."""
    replacements: list[tuple[str, str]] = []

    # Summary replacement
    if original.summary and adapted.summary and original.summary != adapted.summary:
        replacements.append((original.summary[:80], adapted.summary[:80]))

    # Experience description replacements
    for orig_exp, new_exp in zip(original.experience, adapted.experience):
        if orig_exp.description != new_exp.description:
            orig_lines = [l.strip().lstrip("-•* ").strip() for l in orig_exp.description.split("\n") if l.strip()]
            new_lines = [l.strip().lstrip("-•* ").strip() for l in new_exp.description.split("\n") if l.strip()]
            for ol, nl in zip(orig_lines, new_lines):
                if ol and nl and ol != nl:
                    replacements.append((ol[:60], nl[:60]))

    for page in doc:
        for old_text, new_text in replacements:
            text_instances = page.search_for(old_text)
            for inst in text_instances:
                page.add_redact_annot(inst, text=new_text, fontsize=0)
        page.apply_redactions()

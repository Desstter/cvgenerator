import re
import uuid
import fitz
from io import BytesIO
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.config import settings
from app.models.schemas import CVData

# Month abbreviations keyed by lowercase source token, per target language.
_MONTHS_TO_EN = {
    "ene": "Jan", "enero": "Jan", "feb": "Feb", "febrero": "Feb",
    "mar": "Mar", "marzo": "Mar", "abr": "Apr", "abril": "Apr",
    "may": "May", "mayo": "May", "jun": "Jun", "junio": "Jun",
    "jul": "Jul", "julio": "Jul", "ago": "Aug", "agosto": "Aug",
    "sep": "Sep", "sept": "Sep", "septiembre": "Sep",
    "oct": "Oct", "octubre": "Oct", "nov": "Nov", "noviembre": "Nov",
    "dic": "Dec", "diciembre": "Dec",
}
_MONTHS_TO_ES = {
    "jan": "Ene", "january": "Ene", "feb": "Feb", "february": "Feb",
    "mar": "Mar", "march": "Mar", "apr": "Abr", "april": "Abr",
    "may": "May", "jun": "Jun", "june": "Jun", "jul": "Jul", "july": "Jul",
    "aug": "Ago", "august": "Ago", "sep": "Sep", "sept": "Sep", "september": "Sep",
    "oct": "Oct", "october": "Oct", "nov": "Nov", "november": "Nov",
    "dec": "Dic", "december": "Dic",
}
_LOCATION_TO_EN = {"remoto": "Remote", "híbrido": "Hybrid", "hibrido": "Hybrid", "presencial": "On-site"}
_LOCATION_TO_ES = {"remote": "Remoto", "hybrid": "Híbrido", "on-site": "Presencial", "onsite": "Presencial"}
# Language names + proficiency levels, keyed by lowercase source token.
_LANG_TO_EN = {
    "español": "Spanish", "espanol": "Spanish", "inglés": "English", "ingles": "English",
    "francés": "French", "frances": "French", "alemán": "German", "aleman": "German",
    "portugués": "Portuguese", "portugues": "Portuguese", "italiano": "Italian",
    "nativo": "Native", "nativa": "Native", "fluido": "Fluent", "fluida": "Fluent",
    "avanzado": "Advanced", "avanzada": "Advanced", "intermedio": "Intermediate",
    "intermedia": "Intermediate", "básico": "Basic", "basico": "Basic",
    "profesional": "Professional",
}
_LANG_TO_ES = {
    "spanish": "Español", "english": "Inglés", "french": "Francés", "german": "Alemán",
    "portuguese": "Portugués", "italian": "Italiano",
    "native": "Nativo", "fluent": "Fluido", "advanced": "Avanzado",
    "intermediate": "Intermedio", "basic": "Básico", "professional": "Profesional",
}

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]+")


def _translate_tokens(text: str, mapping: dict[str, str]) -> str:
    """Replace whole alpha words found in mapping (case-insensitive), preserving the rest."""
    if not text:
        return text
    return _WORD_RE.sub(lambda m: mapping.get(m.group(0).lower(), m.group(0)), text)


def _localize_cv(cv: CVData) -> CVData:
    """Translate immutable-but-language-dependent fields (dates, location, languages)
    to match the CV's detected language. Returns a copy; original is untouched."""
    lang = cv.detected_language
    if lang not in ("es", "en"):
        return cv

    months = _MONTHS_TO_EN if lang == "en" else _MONTHS_TO_ES
    location = _LOCATION_TO_EN if lang == "en" else _LOCATION_TO_ES
    langmap = _LANG_TO_EN if lang == "en" else _LANG_TO_ES

    out = cv.model_copy(deep=True)
    for exp in out.experience:
        exp.dates = _translate_tokens(exp.dates, months)
        exp.location = _translate_tokens(exp.location, location)
    for edu in out.education:
        edu.dates = _translate_tokens(edu.dates, months)
    out.languages = [_translate_tokens(l, langmap) for l in out.languages]
    return out


def generate_pdf_from_template(
    cv: CVData,
    matched_keywords: list[str] | None = None,
    template_name: str = "modern",
) -> Path:
    """Generate a PDF from an HTML template using xhtml2pdf."""
    cv = _localize_cv(cv)
    env = Environment(loader=FileSystemLoader(str(settings.templates_dir)))
    template = env.get_template(f"{template_name}.html")

    icons_dir = (settings.static_dir / "icons").as_posix()

    html_content = template.render(
        cv=cv,
        matched_keywords=matched_keywords or [],
        icons_dir=icons_dir,
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

import logging
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import uuid
import fitz
from io import BytesIO
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa

from app.config import settings
from app.models.schemas import CVData

logger = logging.getLogger(__name__)

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


def _slugify(text: str, max_len: int = 40) -> str:
    """ASCII-safe, underscore-separated slug for filenames."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:max_len].strip("_")


def _build_filename(cv: CVData, job_title: str = "") -> str:
    """Recruiter-facing filename: CV_Name_Surname_Job_Title.pdf."""
    parts = ["CV"]
    name_slug = _slugify(cv.contact.name)
    if name_slug:
        parts.append(name_slug)
    title_slug = _slugify(job_title)
    if title_slug:
        parts.append(title_slug)
    if len(parts) == 1:
        parts.append(uuid.uuid4().hex[:8])
    return "_".join(parts) + ".pdf"


def _find_chromium() -> str | None:
    """Locate a Chromium-based browser for high-quality HTML→PDF rendering."""
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("chromium"),
        shutil.which("google-chrome"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _render_pdf(html_content: str, output_path: Path) -> None:
    """Render HTML to PDF with a headless Chromium browser (full modern CSS, clickable
    links, proper fonts and page breaks). Falls back to xhtml2pdf if no browser is found."""
    browser = _find_chromium()
    if browser:
        tmp_dir = Path(tempfile.mkdtemp(prefix="cvgen_"))
        html_file = tmp_dir / "cv.html"
        try:
            html_file.write_text(html_content, encoding="utf-8")
            cmd = [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={tmp_dir / 'profile'}",
                f"--print-to-pdf={output_path}",
                html_file.as_uri(),
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            if output_path.exists() and output_path.stat().st_size > 0:
                return
            logger.warning(
                "Chromium PDF rendering failed (rc=%s), falling back to xhtml2pdf: %s",
                result.returncode, result.stderr.decode(errors="replace")[-300:],
            )
        except (OSError, subprocess.SubprocessError):
            logger.exception("Chromium PDF rendering crashed, falling back to xhtml2pdf")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    with open(str(output_path), "wb") as f:
        pisa_status = pisa.CreatePDF(html_content, dest=f)
        if pisa_status.err:
            raise RuntimeError(f"PDF generation failed with {pisa_status.err} errors")


def generate_pdf_from_template(
    cv: CVData,
    matched_keywords: list[str] | None = None,
    template_name: str = "modern",
    job_title: str = "",
) -> Path:
    """Generate a PDF from an HTML template."""
    cv = _localize_cv(cv)
    env = Environment(loader=FileSystemLoader(str(settings.templates_dir)))
    template = env.get_template(f"{template_name}.html")

    icons_dir = (settings.static_dir / "icons").as_posix()

    html_content = template.render(
        cv=cv,
        matched_keywords=matched_keywords or [],
        icons_dir=icons_dir,
    )

    output_path = settings.outputs_dir / _build_filename(cv, job_title)
    _render_pdf(html_content, output_path)
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

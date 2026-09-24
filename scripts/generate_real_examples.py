"""Generate the four audited example resumes from the verified job catalog."""

import argparse
import json
import shutil
import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.models.schemas import CVData
from app.services.ai_adapter import analyze_and_adapt, get_provider, refine_cv
from app.services.ats_optimizer import analyze_keyword_match, reorder_skills
from app.services.base_cv_store import build_real_context, get_profile_definition, load_base_cv
from app.services.claim_guard import review_claims, sanitize_adaptation
from app.services.opportunity_store import list_opportunities
from app.services.pdf_generator import generate_pdf_from_template


FINAL_DIR = ROOT / "output" / "pdf"
MANIFEST_PATH = ROOT / "output" / "real_offers_manifest.json"


def _slug(value: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_")


def _compact(cv):
    compact = cv.model_copy(deep=True)
    for index, entry in enumerate(compact.experience):
        limit = 3 if index == 0 else 2
        entry.description = "\n".join(entry.description.splitlines()[:limit])
    return compact


def generate_one(item, provider, refine: bool) -> dict:
    profile = get_profile_definition(item.profile_id)
    store = load_base_cv(item.profile_id)
    original = store.cv
    real_context = build_real_context(store)

    print(f"[{item.id}] AI adaptation pass 1", flush=True)
    job, adapted, equivalences = analyze_and_adapt(
        provider,
        original,
        item.job_description,
        real_context=real_context,
        profile_type=profile.profile_type,
    )
    if refine:
        print(f"[{item.id}] recruiter refinement pass 2", flush=True)
        adapted = refine_cv(provider, adapted, job, profile_type=profile.profile_type)

    adapted = sanitize_adaptation(original, adapted, profile_type=profile.profile_type)
    claim_review = review_claims(
        original,
        adapted,
        real_context=real_context,
        profile_type=profile.profile_type,
    )
    if claim_review.status != "passed":
        raise RuntimeError(
            f"{item.id}: truth review blocked output: "
            + "; ".join(claim_review.unsupported_claims)
        )

    keywords = job.required_skills + job.preferred_skills + job.keywords
    original_score = analyze_keyword_match(
        original,
        job,
        extra_synonyms=equivalences,
        profile_type=profile.profile_type,
    )
    adapted.skills = reorder_skills(
        adapted.skills,
        keywords,
        extra_synonyms=equivalences,
        profile_type=profile.profile_type,
    )
    final_score = analyze_keyword_match(
        adapted,
        job,
        extra_synonyms=equivalences,
        profile_type=profile.profile_type,
    )

    try:
        generated = generate_pdf_from_template(
            adapted,
            matched_keywords=final_score.matched_keywords,
            template_name=profile.default_template,
            job_title=f"{item.company} {item.title}",
            max_pages=profile.max_pages,
        )
        compacted = False
    except ValueError as exc:
        if "requires at most" not in str(exc):
            raise
        adapted = _compact(adapted)
        generated = generate_pdf_from_template(
            adapted,
            matched_keywords=final_score.matched_keywords,
            template_name=profile.default_template,
            job_title=f"{item.company} {item.title}",
            max_pages=profile.max_pages,
        )
        compacted = True

    final_name = (
        f"CV_{_slug(adapted.contact.name)}_{_slug(item.company)}_{_slug(item.title)}.pdf"
    )
    final_path = FINAL_DIR / final_name
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated, final_path)

    with fitz.open(final_path) as document:
        page_count = document.page_count
        text = "\n".join(page.get_text() for page in document)

    print(
        f"[{item.id}] {page_count} page | ATS {original_score.overall_score:.0f}% -> "
        f"{final_score.overall_score:.0f}% | {final_path.name}",
        flush=True,
    )
    return {
        "id": item.id,
        "profile_id": item.profile_id,
        "company": item.company,
        "title": item.title,
        "location": item.location,
        "source_url": item.source_url,
        "checked_at": item.checked_at,
        "fit_note": item.fit_note,
        "template": profile.default_template,
        "compacted": compacted,
        "claim_review": claim_review.model_dump(),
        "ats_before": original_score.model_dump(),
        "ats_after": final_score.model_dump(),
        "page_count": page_count,
        "extracted_text_characters": len(text),
        "pdf": str(final_path.resolve()),
        "adapted_cv": adapted.model_dump(exclude={"raw_markdown"}),
    }


def rerender_one(item, record: dict) -> dict:
    """Reapply deterministic guards and the latest template without another AI call."""
    profile = get_profile_definition(item.profile_id)
    store = load_base_cv(item.profile_id)
    adapted = CVData.model_validate(record["adapted_cv"])
    adapted = sanitize_adaptation(store.cv, adapted, profile_type=profile.profile_type)
    review = review_claims(
        store.cv,
        adapted,
        real_context=build_real_context(store),
        profile_type=profile.profile_type,
    )
    if review.status != "passed":
        raise RuntimeError(f"{item.id}: truth review blocked rerender")
    generated = generate_pdf_from_template(
        adapted,
        matched_keywords=record.get("ats_after", {}).get("matched_keywords", []),
        template_name=profile.default_template,
        job_title=f"{item.company} {item.title}",
        max_pages=profile.max_pages,
    )
    final_path = Path(record["pdf"])
    shutil.copy2(generated, final_path)
    with fitz.open(final_path) as document:
        record["page_count"] = document.page_count
        record["extracted_text_characters"] = len(
            "\n".join(page.get_text() for page in document)
        )
    record["template"] = profile.default_template
    record["claim_review"] = review.model_dump()
    record["adapted_cv"] = adapted.model_dump(exclude={"raw_markdown"})
    print(f"[{item.id}] rerendered | {record['page_count']} page | {final_path.name}", flush=True)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=settings.ai_provider)
    parser.add_argument("--skip-refine", action="store_true")
    parser.add_argument("--rerender-only", action="store_true")
    parser.add_argument("--id", action="append", dest="ids")
    args = parser.parse_args()

    selected = list_opportunities()
    if args.ids:
        selected = [item for item in selected if item.id in set(args.ids)]
    if not selected:
        raise SystemExit("No catalog opportunities selected")

    if args.rerender_only:
        if not MANIFEST_PATH.exists():
            raise SystemExit("The manifest does not exist; generate AI examples first")
        previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in previous}
        results = [rerender_one(item, by_id[item.id]) for item in selected]
    else:
        provider = get_provider(args.provider)
        results = [generate_one(item, provider, not args.skip_refine) for item in selected]
    if MANIFEST_PATH.exists():
        try:
            previous = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = []
        by_id = {item["id"]: item for item in previous if isinstance(item, dict) and item.get("id")}
        by_id.update({item["id"]: item for item in results})
        results = [by_id[item.id] for item in list_opportunities() if item.id in by_id]
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Manifest: {MANIFEST_PATH.resolve()}", flush=True)


if __name__ == "__main__":
    main()

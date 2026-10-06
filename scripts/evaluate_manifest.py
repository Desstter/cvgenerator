"""Offline quality audit of generated real-offer examples; never calls an AI API."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.schemas import CVData
from app.services.base_cv_store import build_real_context, get_profile_definition, load_base_cv
from app.services.claim_guard import review_claims
from app.services.cv_quality import editorial_issues
from app.services.opportunity_store import list_opportunities
from app.services.pdf_generator import verify_pdf_content


def evaluate(manifest: Path) -> list[dict]:
    records = json.loads(manifest.read_text(encoding="utf-8"))
    opportunities = {item.id: item for item in list_opportunities()}
    results = []
    for record in records:
        opportunity = opportunities[record["id"]]
        profile = get_profile_definition(opportunity.profile_id)
        store = load_base_cv(opportunity.profile_id)
        cv = CVData.model_validate(record["adapted_cv"])
        review = review_claims(store.cv, cv, build_real_context(store), profile.profile_type)
        pdf_error = ""
        try:
            verify_pdf_content(Path(record["pdf"]), cv, record["template"], profile.max_pages)
        except (OSError, ValueError) as exc:
            pdf_error = str(exc)
        results.append({
            "id": record["id"],
            "pdf_valid": not pdf_error,
            "pdf_error": pdf_error,
            "claim_status": review.status,
            "unsupported_claims": review.unsupported_claims,
            "claims_requiring_human_review": len(review.review_items),
            "editorial_issues": editorial_issues(cv),
            "stored_coverage": record.get("ats_after", {}).get("overall_score"),
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "output" / "real_offers_manifest.json")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.manifest), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

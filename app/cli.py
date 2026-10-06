"""Headless, JSON-only interface to the existing CV pipeline.

Each invocation uses an explicit candidate workspace. No HTTP server, browser UI,
or outbound job submission is needed. AI generation uses the configured provider.
"""

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


PROFILE_FILES = {"developer": "base_cv.json", "bilingual_customer_service": "base_cv_bilingual.json"}
STATES = ("discovered", "shortlisted", "cv_ready", "prepared", "awaiting_user",
          "submitting", "submitted", "uncertain", "skipped", "failed")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def configure_workspace(path):
    """Must run before importing app.config or any service that caches data paths."""
    root = Path(path).expanduser().resolve()
    os.environ.update({
        "CV_DATA_DIR": str(root / "data"), "OUTPUTS_DIR": str(root / "generated"),
        "SAVED_DIR": str(root / "saved"), "UPLOADS_DIR": str(root / "uploads"),
        "ORT_DISABLE_TELEMETRY": "1",
    })
    # The CLI is one workspace per process; switching cached settings is unsafe.
    loaded = sys.modules.get("app.config")
    if loaded and loaded.settings.cv_data_dir.resolve() != root / "data":
        raise ValueError("Use a fresh CLI process when changing candidate workspace")
    root.mkdir(parents=True, exist_ok=True)
    return root


def require_candidate(root, profile):
    path = root / "data" / PROFILE_FILES[profile]
    if not path.is_file():
        raise ValueError("Initialize this candidate explicitly with init --candidate; packaged personal profiles are never used by the CLI")
    from app.models.schemas import BaseCVStore
    from app.services.cv_analyzer import critical_cv_errors, validate_cv_data
    store = BaseCVStore.model_validate(read_json(path))
    if store.profile_id != profile:
        raise ValueError("Candidate profile does not match --profile")
    errors = critical_cv_errors(store.cv)
    if not store.cv.contact.email.strip():
        errors.append("Candidate email is missing")
    errors.extend(issue for issue in validate_cv_data(store.cv) if "Invalid email" in issue)
    if errors:
        raise ValueError("Invalid candidate: " + "; ".join(errors))
    return store


def record_for(record_id, profile):
    from app.services.history import load_application
    from app.services.base_cv_store import load_base_cv
    record = load_application(record_id)
    if not record or not record.get("snapshot"):
        raise ValueError("CV record not found in this workspace")
    if record["profile_id"] != profile:
        raise ValueError("CV record belongs to a different profile")
    candidate = load_base_cv(profile).cv.contact
    saved_contact = record["snapshot"]["source_cv"].get("contact", {})
    if candidate.name != saved_contact.get("name") or candidate.email != saved_contact.get("email"):
        raise ValueError("This CV belongs to a different candidate identity")
    return record


def record_fingerprint(record):
    return fingerprint({"record_id": record["id"], "snapshot": record["snapshot"]})


def inspect_record(root, record):
    from app.models.schemas import CVData
    from app.services.base_cv_store import get_profile_definition
    from app.services.cv_quality import editorial_issues
    from app.services.pdf_generator import verify_pdf_content
    snapshot = record["snapshot"]
    cv = CVData.model_validate(snapshot["adapted_cv"])
    definition = get_profile_definition(record["profile_id"])
    pdf = root / "saved" / Path(record["pdf_filename"]).name
    pdf_error = ""
    try:
        verify_pdf_content(pdf, cv, snapshot["template"], definition.max_pages)
    except (OSError, ValueError) as exc:
        pdf_error = str(exc)
    issues = editorial_issues(cv)
    return {
        "record_id": record["id"], "record_fingerprint": record_fingerprint(record),
        "reviewed": record["reviewed"], "claim_review": snapshot["claim_review"],
        "quality": {
            "pdf_valid": not pdf_error, "pdf_error": pdf_error, "editorial_issues": issues,
            "keyword_coverage": snapshot["coverage_after"],
            "note": "Local keyword coverage is not a hiring probability or an external ATS score. Agent review must evaluate relevance, factual support and presentation separately.",
        },
        "source_cv": snapshot["source_cv"], "adapted_cv": snapshot["adapted_cv"],
        "job_analysis": snapshot["job_analysis"], "real_context": snapshot.get("real_context", ""),
        "pdf_path": str(pdf),
        "review_template": {
            "record_id": record["id"], "record_fingerprint": record_fingerprint(record),
            "reviewer": "", "decisions": [
                {"field": item["field"], "decision": "unresolved", "evidence_quote": "", "reason": ""}
                for item in snapshot["claim_review"].get("review_items", [])
            ],
        },
    }


def confirm_review(root, record, review):
    from app import main as api
    from app.models.schemas import ClaimConfirmation
    if review.get("record_id") != record["id"] or review.get("record_fingerprint") != record_fingerprint(record):
        raise ValueError("Review is stale or belongs to another CV version; run inspect again")
    if not review.get("reviewer", "").strip():
        raise ValueError("Review must identify the reviewer")
    items = record["snapshot"]["claim_review"].get("review_items", [])
    expected = {item["field"] for item in items}
    decisions = review.get("decisions", [])
    if len(decisions) != len(expected) or {item.get("field") for item in decisions} != expected:
        raise ValueError("Provide exactly one decision for each rewritten claim")
    source = record["snapshot"]["source_cv"]
    evidence_text = "\n".join(_strings(source)) + "\n" + record["snapshot"].get("real_context", "")
    for decision in decisions:
        quote = decision.get("evidence_quote", "").strip()
        if decision.get("decision") != "supported" or not decision.get("reason", "").strip():
            raise ValueError("Unresolved/rejected claims must be corrected with revise before confirmation")
        if not quote or quote.casefold() not in evidence_text.casefold():
            raise ValueError("Every approval needs an exact evidence quote from source_cv or verified real_context")
    asyncio.run(api.confirm_history_entry(record["id"], ClaimConfirmation(fields=sorted(expected))))
    write_json(root / "reviews" / f"{record['id']}.json", {**review, "reviewed_at": now()})
    return {"record_id": record["id"], "reviewed": True}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Job source_url must be an HTTPS URL without credentials")
    host = parsed.hostname.lower()
    path = parsed.path.rstrip("/")
    # LinkedIn search/referral routes identify the same job by currentJobId.
    query = dict(parse_qsl(parsed.query))
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        import re
        match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)$", path)
        job_id = match.group(1) if match else query.get("currentJobId")
        if job_id and job_id.isdigit():
            return f"https://www.linkedin.com/jobs/view/{job_id}"
    # Preserve ATS identifiers, remove only known referral/analytics parameters.
    kept = sorted((key, value) for key, value in parse_qsl(parsed.query)
                  if not key.lower().startswith("utm_") and key.lower() not in {"trk", "trackingid", "ref", "refid"})
    return urlunsplit(("https", parsed.netloc.lower(), path, urlencode(kept), ""))


def track_application(root, args):
    """A durable ledger; recording a state never performs a browser action."""
    path = root / "applications.json"
    ledger = read_json(path) if path.exists() else []
    job = read_json(args.job)
    for field in ("source_url", "title", "company", "description"):
        if not isinstance(job.get(field), str) or not job[field].strip():
            raise ValueError(f"Job snapshot requires {field}")
    url = canonical_url(job["source_url"])
    key = fingerprint({"profile": args.profile, "url": url})[:20]
    entry = next((item for item in ledger if item["key"] == key), None)
    if entry and entry["state"] == "submitted":
        raise ValueError("Already submitted: duplicate applications are blocked")
    if entry and entry["state"] in {"submitting", "uncertain"} and args.state not in {"submitted", "uncertain", "failed"}:
        raise ValueError("Submission status is uncertain: inspect the portal before retrying")
    previous = entry["state"] if entry else None
    allowed = {
        None: {"discovered", "skipped"},
        "discovered": {"discovered", "shortlisted", "skipped", "awaiting_user", "failed"},
        "shortlisted": {"shortlisted", "cv_ready", "skipped", "awaiting_user", "failed"},
        "cv_ready": {"cv_ready", "prepared", "awaiting_user", "skipped", "failed"},
        "prepared": {"prepared", "submitting", "awaiting_user", "failed", "skipped"},
        "awaiting_user": {"awaiting_user", "shortlisted", "cv_ready", "prepared", "skipped", "failed"},
        "submitting": {"submitted", "uncertain", "failed"},
        "uncertain": {"submitted", "uncertain", "failed"},
        "failed": {"failed", "discovered", "shortlisted", "cv_ready", "prepared", "skipped"},
        "skipped": {"skipped", "discovered"},
    }
    if args.state not in allowed.get(previous, set()):
        raise ValueError(f"Invalid transition: {previous} -> {args.state}")
    record_id = args.record or (entry or {}).get("record_id", "")
    if previous in {"submitting", "uncertain"} and record_id != entry.get("record_id"):
        raise ValueError("Do not change the CV version while reconciling a submission")
    if args.state in {"cv_ready", "prepared", "submitting", "submitted"}:
        if not record_id:
            raise ValueError("This state requires --record for the reviewed CV version")
        record = record_for(record_id, args.profile)
        report = inspect_record(root, record)
        if not record["reviewed"] or record["snapshot"]["claim_review"]["status"] == "blocked" or not report["quality"]["pdf_valid"]:
            raise ValueError("CV must pass factual review and PDF validation first")
        if record["snapshot"]["job_description"].strip() != job["description"].strip():
            raise ValueError("CV was generated for a different job description")
    evidence = read_json(args.evidence) if args.evidence else None
    if args.state == "submitted":
        if not evidence or not all(isinstance(evidence.get(field), str) and evidence[field].strip()
                                   for field in ("confirmation_text", "observed_at", "destination_url")):
            raise ValueError("Submitted requires --evidence with observed_at, destination_url and confirmation_text")
        canonical_url(evidence["destination_url"])
        observed = datetime.fromisoformat(evidence["observed_at"].replace("Z", "+00:00"))
        if observed.utcoffset() is None:
            raise ValueError("Receipt observed_at must include a timezone")
    if args.state == "failed" and previous in {"submitting", "uncertain"}:
        if not evidence or not evidence.get("not_submitted_verified") or not evidence.get("confirmation_text"):
            raise ValueError("Before retrying, supply evidence that the portal did not receive the application")
    event = {"state": args.state, "at": now(), "note": args.note, "record_id": record_id, "evidence": evidence}
    if entry is None:
        entry = {"key": key, "profile_id": args.profile, "canonical_url": url, "job": job, "events": []}
        ledger.append(entry)
    entry.update({"state": args.state, "record_id": record_id, "updated_at": event["at"]})
    entry["events"].append(event)
    write_json(path, ledger)
    return entry


def parser():
    cli = argparse.ArgumentParser(description="Generate, inspect, revise and export CVs without the GUI. Output: JSON; errors: stderr + exit 1.")
    cli.add_argument("--workspace", required=True, type=Path, help="Private, persistent directory for exactly one candidate")
    cli.add_argument("--profile", default="developer", choices=PROFILE_FILES)
    cli.add_argument("--json-out", type=Path, help="Also save the JSON result to a file")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Import a verified BaseCVStore into an empty candidate workspace")
    init.add_argument("--candidate", required=True, type=Path)
    commands.add_parser("doctor", help="Report configured providers and isolated paths; never print keys")
    commands.add_parser("profile", help="Export this workspace's verified candidate JSON")
    update = commands.add_parser("profile-update", help="Update verified facts for the same candidate; preserves a revision")
    update.add_argument("--candidate", required=True, type=Path)
    generate = commands.add_parser("generate", help="Adapt to a UTF-8 job description; calls the configured AI provider")
    generate.add_argument("--job", required=True, type=Path)
    generate.add_argument("--provider", choices=("claude", "openai", "gemini"))
    generate.add_argument("--template", choices=("modern", "classic", "technical", "bilingual"))
    commands.add_parser("history")
    inspect = commands.add_parser("inspect", help="Read-back PDF QA, factual review, coverage and editable CV")
    inspect.add_argument("--record", required=True)
    revise = commands.add_parser("revise", help="Re-render edited CVData JSON, without another AI call")
    revise.add_argument("--record", required=True)
    revise.add_argument("--cv", required=True, type=Path)
    confirm = commands.add_parser("confirm", help="Record explicit, evidence-backed review of each rewritten claim")
    confirm.add_argument("--record", required=True)
    confirm.add_argument("--review", required=True, type=Path)
    export = commands.add_parser("export", help="Copy a reviewed, validated PDF to the upload location")
    export.add_argument("--record", required=True)
    export.add_argument("--out", required=True, type=Path)
    commands.add_parser("applications", help="Resume the durable job application ledger")
    track = commands.add_parser("track", help="Record a verified state; never sends a job application")
    track.add_argument("--job", required=True, type=Path, help="JSON job snapshot")
    track.add_argument("--state", required=True, choices=STATES)
    track.add_argument("--record", default="")
    track.add_argument("--note", default="")
    track.add_argument("--evidence", type=Path)
    return cli


def execute(args):
    root = configure_workspace(args.workspace)
    if args.command == "doctor":
        from app.config import settings
        return {"workspace": str(root), "candidate_initialized": (root / "data" / PROFILE_FILES[args.profile]).is_file(),
                "default_provider": settings.ai_provider, "refine_pass": settings.refine_pass,
                "keys_configured": {"claude": bool(settings.anthropic_api_key), "openai": bool(settings.openai_api_key), "gemini": bool(settings.google_api_key)},
                "mode": "local pipeline, no HTTP server; browser submission is a separate agent action"}
    if args.command == "init":
        from app.models.schemas import BaseCVStore
        from app.services.base_cv_store import save_base_cv
        target = root / "data" / PROFILE_FILES[args.profile]
        if target.exists():
            raise ValueError("Candidate already initialized; use another workspace rather than overwriting an identity")
        store = BaseCVStore.model_validate(read_json(args.candidate))
        if store.profile_id != args.profile:
            raise ValueError("Candidate profile does not match --profile")
        # Validate before persisting; do not leave half-initialized workspaces.
        from app.services.cv_analyzer import critical_cv_errors, validate_cv_data
        errors = critical_cv_errors(store.cv)
        if not store.cv.contact.email.strip():
            errors.append("Candidate email is missing")
        errors.extend(issue for issue in validate_cv_data(store.cv) if "Invalid email" in issue)
        if errors:
            raise ValueError("Invalid candidate: " + "; ".join(errors))
        save_base_cv(store, args.profile)
        return {"workspace": str(root), "profile_id": args.profile, "candidate_file": str(target), "initialized": True}
    store = require_candidate(root, args.profile)
    if args.command == "profile-update":
        from app.models.schemas import BaseCVStore
        from app.services.base_cv_store import save_base_cv
        from app.services.cv_analyzer import critical_cv_errors
        updated = BaseCVStore.model_validate(read_json(args.candidate))
        if updated.profile_id != args.profile or updated.cv.contact != store.cv.contact:
            raise ValueError("Profile update must preserve candidate contact and profile; use another workspace for another identity")
        errors = critical_cv_errors(updated.cv)
        if errors:
            raise ValueError("Invalid candidate: " + "; ".join(errors))
        save_base_cv(updated, args.profile)
        return {"profile_id": args.profile, "updated": True, "revision_dir": str(root / "data" / "revisions")}
    if args.command == "profile":
        return store.model_dump(exclude={"cv": {"raw_markdown"}})
    if args.command == "applications":
        path = root / "applications.json"
        return read_json(path) if path.exists() else []
    if args.command == "track":
        return track_application(root, args)
    if args.command == "history":
        from app.services.history import load_history
        return [{key: value for key, value in item.items() if key != "snapshot"}
                for item in load_history() if item["profile_id"] == args.profile]
    if args.command == "generate":
        from app import main as api
        from app.services.base_cv_store import get_profile_definition
        job = args.job.read_text(encoding="utf-8-sig").strip()
        if not job:
            raise ValueError("Job description is empty")
        definition = get_profile_definition(args.profile)
        return api.adapt_cv_endpoint(job_description=job, file=None,
            template=args.template or definition.default_template, provider_name=args.provider or "",
            profile_id=args.profile, confirmed_cv_json="")
    record = record_for(args.record, args.profile)
    if args.command == "inspect":
        return inspect_record(root, record)
    if args.command == "confirm":
        return confirm_review(root, record, read_json(args.review))
    if args.command == "revise":
        from app import main as api
        from app.models.schemas import CVData
        return api.revise_history_entry(args.record, CVData.model_validate(read_json(args.cv)))
    if args.command == "export":
        from app import main as api
        report = inspect_record(root, record)
        if not report["quality"]["pdf_valid"]:
            raise ValueError(report["quality"]["pdf_error"])
        response = asyncio.run(api.download_pdf(record["pdf_filename"]))
        target = args.out.expanduser().resolve()
        source = Path(response.path).resolve()
        # The API may choose generated/ ahead of saved/. Validate the exact bytes
        # being exported, even if the persistent saved copy was already checked.
        from app.models.schemas import CVData
        from app.services.base_cv_store import get_profile_definition
        from app.services.pdf_generator import verify_pdf_content
        verify_pdf_content(source, CVData.model_validate(record["snapshot"]["adapted_cv"]),
                           record["snapshot"]["template"], get_profile_definition(args.profile).max_pages)
        if target.exists() and target != source:
            raise ValueError("Export target already exists; choose a new filename")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target != source:
            shutil.copy2(source, target)
        return {"record_id": args.record, "pdf_path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    raise ValueError("Unknown command")


def main(argv=None):
    # Avoid Windows console encoding changing JSON, accented CV text or logs.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        if args.json_out:
            write_json(args.json_out, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        detail = getattr(exc, "detail", str(exc))
        print(json.dumps({"error": detail, "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

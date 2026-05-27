import json
import uuid
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "data" / "history.json"


def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_application(
    job_title: str,
    company: str,
    ats_score: float,
    required_score: float,
    preferred_score: float,
    pdf_filename: str,
    detected_language: str,
) -> dict:
    history = load_history()
    record = {
        "id": uuid.uuid4().hex[:8],
        "date": datetime.now().isoformat(),
        "job_title": job_title or "Unknown Role",
        "company": company or "Unknown Company",
        "ats_score": round(ats_score, 1),
        "required_score": round(required_score, 1),
        "preferred_score": round(preferred_score, 1),
        "pdf_filename": pdf_filename,
        "detected_language": detected_language,
    }
    history.insert(0, record)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def delete_application(record_id: str) -> bool:
    history = load_history()
    new_history = [r for r in history if r["id"] != record_id]
    if len(new_history) == len(history):
        return False
    HISTORY_FILE.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

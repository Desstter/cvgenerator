import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from app.config import settings

HISTORY_FILE = settings.cv_data_dir / "history.json"
_history_lock = threading.Lock()


def _write_history(history: list[dict]) -> None:
    """Replace the history atomically so an interrupted write keeps the old file."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = HISTORY_FILE.with_name(f".{HISTORY_FILE.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, HISTORY_FILE)
    finally:
        temporary.unlink(missing_ok=True)


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
    profile_id: str = "developer",
) -> dict:
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
        "profile_id": profile_id,
    }
    with _history_lock:
        history = load_history()
        history.insert(0, record)
        _write_history(history)
    return record


def delete_application(record_id: str) -> bool:
    with _history_lock:
        history = load_history()
        new_history = [r for r in history if r["id"] != record_id]
        if len(new_history) == len(history):
            return False
        _write_history(new_history)
        return True

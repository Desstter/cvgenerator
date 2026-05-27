"""Persistent, editable store for Santiago's base CV.

The base CV lives in base_cv.json so it can be edited from the UI. On first run
(no JSON yet) it is seeded from the hardcoded data in app/data/base_cv.py, which
remains the canonical fallback.
"""

import json
from pathlib import Path

from app.models.schemas import BaseCVStore, ExperienceContextEntry
from app.data.base_cv import get_base_cv, EXPERIENCE_CONTEXT

STORE_FILE = Path(__file__).resolve().parent.parent / "data" / "base_cv.json"


def _seed() -> BaseCVStore:
    """Build the initial store from the hardcoded base CV data."""
    return BaseCVStore(
        cv=get_base_cv(),
        experience_context={
            company: ExperienceContextEntry(**ctx)
            for company, ctx in EXPERIENCE_CONTEXT.items()
        },
    )


def load_base_cv() -> BaseCVStore:
    """Load the editable base CV, seeding and persisting it on first run."""
    if not STORE_FILE.exists():
        store = _seed()
        save_base_cv(store)
        return store
    try:
        data = json.loads(STORE_FILE.read_text(encoding="utf-8"))
        return BaseCVStore.model_validate(data)
    except (json.JSONDecodeError, OSError, ValueError):
        return _seed()


def save_base_cv(store: BaseCVStore) -> BaseCVStore:
    """Persist the base CV store to JSON."""
    STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(
        store.model_dump_json(indent=2, exclude={"cv": {"raw_markdown"}}),
        encoding="utf-8",
    )
    return store


def build_real_context(store: BaseCVStore) -> str:
    """Build the real-context string fed to the AI from the stored experience context."""
    lines = []
    for company, ctx in store.experience_context.items():
        lines.append(f"\n--- {company} ---")
        lines.append(f"REAL technologies used: {', '.join(ctx.real_technologies)}")
        lines.append("REAL achievements:")
        for a in ctx.real_achievements:
            lines.append(f"  - {a}")
    return "\n".join(lines)

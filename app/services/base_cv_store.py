"""Persistent stores for the independent CV profiles used by the application."""

import json
from pathlib import Path

from app.models.schemas import (
    BaseCVStore,
    ExperienceContextEntry,
    ProfileDefinition,
)
from app.data.base_cv import get_base_cv, EXPERIENCE_CONTEXT
from app.config import settings

DATA_DIR = settings.cv_data_dir
PACKAGED_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

PROFILE_DEFINITIONS: dict[str, ProfileDefinition] = {
    "developer": ProfileDefinition(
        id="developer",
        display_name="Developer",
        description="Software development, engineering and technical leadership roles.",
        profile_type="developer",
        default_template="technical",
        content_language="es",
        max_pages=1,
    ),
    "bilingual_customer_service": ProfileDefinition(
        id="bilingual_customer_service",
        display_name="Bilingual Customer Service",
        description="Entry-level bilingual customer service and technical support roles.",
        profile_type="bpo",
        default_template="bilingual",
        content_language="en",
        one_page_required=True,
        max_pages=1,
    ),
}

PROFILE_FILES = {
    "developer": DATA_DIR / "base_cv.json",
    "bilingual_customer_service": DATA_DIR / "base_cv_bilingual.json",
}


def get_profile_definition(profile_id: str = "developer") -> ProfileDefinition:
    try:
        return PROFILE_DEFINITIONS[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown CV profile: {profile_id}") from exc


def list_profile_definitions() -> list[ProfileDefinition]:
    return list(PROFILE_DEFINITIONS.values())


def _seed_developer() -> BaseCVStore:
    definition = PROFILE_DEFINITIONS["developer"]
    return BaseCVStore(
        profile_id=definition.id,
        display_name=definition.display_name,
        profile_type=definition.profile_type,
        cv=get_base_cv(),
        experience_context={
            company: ExperienceContextEntry(**ctx)
            for company, ctx in EXPERIENCE_CONTEXT.items()
        },
    )


def _seed(profile_id: str) -> BaseCVStore:
    if profile_id == "developer":
        return _seed_developer()
    # Never silently substitute the developer identity for the BPO identity.
    raise ValueError(f"Base data for profile '{profile_id}' is unavailable")


def load_base_cv(profile_id: str = "developer") -> BaseCVStore:
    """Load one profile without falling back to a different identity."""
    definition = get_profile_definition(profile_id)
    store_file = PROFILE_FILES[profile_id]
    if not store_file.exists():
        packaged_file = PACKAGED_DATA_DIR / store_file.name
        if packaged_file != store_file and packaged_file.exists():
            store = BaseCVStore.model_validate_json(packaged_file.read_text(encoding="utf-8"))
        else:
            store = _seed(profile_id)
        save_base_cv(store, profile_id)
        return store
    try:
        data = json.loads(store_file.read_text(encoding="utf-8"))
        store = BaseCVStore.model_validate(data)
        store.profile_id = definition.id
        store.display_name = definition.display_name
        store.profile_type = definition.profile_type
        return store
    except (json.JSONDecodeError, OSError, ValueError):
        if profile_id == "developer":
            return _seed_developer()
        raise ValueError(f"The '{profile_id}' CV data file is invalid")


def save_base_cv(store: BaseCVStore, profile_id: str | None = None) -> BaseCVStore:
    """Persist exactly one profile, preventing cross-profile overwrites."""
    target_id = profile_id or store.profile_id
    definition = get_profile_definition(target_id)
    if store.profile_id not in (target_id, ""):
        raise ValueError("Profile payload does not match the selected profile")

    store.profile_id = definition.id
    store.display_name = definition.display_name
    store.profile_type = definition.profile_type
    store_file = PROFILE_FILES[target_id]
    store_file.parent.mkdir(parents=True, exist_ok=True)
    store_file.write_text(
        store.model_dump_json(indent=2, exclude={"cv": {"raw_markdown"}}),
        encoding="utf-8",
    )
    return store


def build_real_context(store: BaseCVStore) -> str:
    """Build interview-defensible context sent to the AI but not printed."""
    lines = [
        f"PROFILE TYPE: {store.profile_type}",
        "Everything below is verified source material. Do not invent beyond it.",
    ]
    for company, ctx in store.experience_context.items():
        lines.append(f"\n--- {company} ---")
        if ctx.real_technologies:
            lines.append(f"REAL technologies/tools used: {', '.join(ctx.real_technologies)}")
        lines.append("REAL achievements and transferable evidence:")
        for achievement in ctx.real_achievements:
            lines.append(f"  - {achievement}")
    return "\n".join(lines)

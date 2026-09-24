"""Read-only catalog of real job snapshots used for repeatable CV generation."""

import json
from pathlib import Path

from app.models.schemas import JobOpportunity

CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "job_opportunities.json"


def list_opportunities(profile_id: str | None = None) -> list[JobOpportunity]:
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("The verified job catalog is unavailable or invalid") from exc
    items = [JobOpportunity.model_validate(item) for item in payload]
    if profile_id:
        items = [item for item in items if item.profile_id == profile_id]
    return items


def get_opportunity(opportunity_id: str) -> JobOpportunity:
    for item in list_opportunities():
        if item.id == opportunity_id:
            return item
    raise ValueError(f"Unknown job opportunity: {opportunity_id}")

"""Asset lifecycle/compliance trail writer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.people.assets.audit import AssetLifecycleEvent

try:
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    UTC = timezone.utc


def record_asset_lifecycle_event(
    db: Session,
    *,
    org_id: UUID,
    asset_id: UUID,
    event_category: str,
    event_type: str,
    actor_user_id: UUID | None = None,
    source_type: str | None = None,
    source_record_id: UUID | None = None,
    previous_status: str | None = None,
    new_status: str | None = None,
    previous_location_id: UUID | None = None,
    new_location_id: UUID | None = None,
    previous_owner_employee_id: UUID | None = None,
    new_owner_employee_id: UUID | None = None,
    notes: str | None = None,
    event_payload: dict[str, Any] | None = None,
    event_at: datetime | None = None,
) -> AssetLifecycleEvent:
    event = AssetLifecycleEvent(
        organization_id=org_id,
        asset_id=asset_id,
        event_category=event_category,
        event_type=event_type,
        actor_user_id=actor_user_id,
        source_type=source_type,
        source_record_id=source_record_id,
        previous_status=previous_status,
        new_status=new_status,
        previous_location_id=previous_location_id,
        new_location_id=new_location_id,
        previous_owner_employee_id=previous_owner_employee_id,
        new_owner_employee_id=new_owner_employee_id,
        notes=notes,
        event_payload=event_payload,
        event_at=event_at or datetime.now(UTC),
    )
    db.add(event)
    return event

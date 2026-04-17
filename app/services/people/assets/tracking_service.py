"""Asset tracking service (QR/Barcode, RFID, GPS)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fixed_assets.asset import Asset
from app.models.people.assets.assignment import (
    AssetAssignment,
    AssetAssignmentMovement,
    AssignmentMovementType,
    AssignmentStatus,
)
from app.models.people.assets.tracking import AssetTrackingEvent, AssetTrackingMethod
from app.services.people.assets.lifecycle_event_service import record_asset_lifecycle_event
from app.services.common import NotFoundError, PaginatedResult, PaginationParams

__all__ = ["AssetTrackingService"]

try:
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    UTC = timezone.utc


class AssetTrackingService:
    """Capture and query asset tracking events."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_asset(self, org_id: UUID, asset_id: UUID) -> Asset:
        asset = self.db.get(Asset, asset_id)
        if not asset or asset.organization_id != org_id:
            raise NotFoundError("Asset not found")
        return asset

    def _get_active_assignment(
        self,
        org_id: UUID,
        asset_id: UUID,
    ) -> AssetAssignment | None:
        return self.db.scalar(
            select(AssetAssignment).where(
                AssetAssignment.organization_id == org_id,
                AssetAssignment.asset_id == asset_id,
                AssetAssignment.status == AssignmentStatus.ISSUED,
            )
        )

    def list_events(
        self,
        org_id: UUID,
        *,
        asset_id: UUID | None = None,
        tracking_method: AssetTrackingMethod | None = None,
        location_id: UUID | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[AssetTrackingEvent]:
        query = select(AssetTrackingEvent).where(AssetTrackingEvent.organization_id == org_id)
        if asset_id:
            query = query.where(AssetTrackingEvent.asset_id == asset_id)
        if tracking_method:
            query = query.where(AssetTrackingEvent.tracking_method == tracking_method)
        if location_id:
            query = query.where(AssetTrackingEvent.location_id == location_id)
        query = query.order_by(AssetTrackingEvent.tracked_at.desc())
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        if pagination:
            query = query.offset(pagination.offset).limit(pagination.limit)
        items = list(self.db.scalars(query).all())
        return PaginatedResult(
            items=items,
            total=total,
            offset=pagination.offset if pagination else 0,
            limit=pagination.limit if pagination else len(items),
        )

    def record_event(
        self,
        org_id: UUID,
        *,
        asset_id: UUID,
        tracking_method: AssetTrackingMethod,
        tracked_at: datetime | None = None,
        tracking_reference: str | None = None,
        location_id: UUID | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        accuracy_meters: float | None = None,
        notes: str | None = None,
        scanned_by_user_id: UUID | None = None,
    ) -> AssetTrackingEvent:
        asset = self._get_asset(org_id, asset_id)
        previous_location_id = asset.location_id
        event_time = tracked_at or datetime.now(UTC)

        movement_logged = False
        if location_id and location_id != asset.location_id:
            active_assignment = self._get_active_assignment(org_id, asset_id)
            asset.location_id = location_id
            self.db.add(
                AssetAssignmentMovement(
                    organization_id=org_id,
                    asset_id=asset_id,
                    assignment_id=active_assignment.assignment_id
                    if active_assignment
                    else None,
                    movement_type=AssignmentMovementType.LOCATION_TRANSFERRED,
                    from_employee_id=active_assignment.employee_id
                    if active_assignment
                    else None,
                    to_employee_id=active_assignment.employee_id if active_assignment else None,
                    from_location_id=previous_location_id,
                    to_location_id=location_id,
                    moved_on=event_time.date(),
                    notes=notes or f"Tracked via {tracking_method.value}",
                    moved_by_user_id=scanned_by_user_id,
                )
            )
            movement_logged = True
            record_asset_lifecycle_event(
                self.db,
                org_id=org_id,
                asset_id=asset.asset_id,
                event_category="LOCATION",
                event_type="LOCATION_CHANGED",
                source_type="asset_tracking_event",
                actor_user_id=scanned_by_user_id,
                previous_location_id=previous_location_id,
                new_location_id=location_id,
                notes=notes or f"Tracked via {tracking_method.value}",
                event_payload={
                    "tracking_method": tracking_method.value,
                    "tracking_reference": tracking_reference,
                },
            )

        event = AssetTrackingEvent(
            organization_id=org_id,
            asset_id=asset_id,
            tracking_method=tracking_method,
            tracking_reference=tracking_reference,
            tracked_at=event_time,
            location_id=location_id,
            previous_location_id=previous_location_id,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy_meters,
            movement_logged=movement_logged,
            scanned_by_user_id=scanned_by_user_id,
            notes=notes,
        )
        self.db.add(event)
        self.db.flush()
        return event

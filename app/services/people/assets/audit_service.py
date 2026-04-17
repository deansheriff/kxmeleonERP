"""Asset compliance and audit workflow service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.fixed_assets.asset import Asset, AssetStatus
from app.models.people.assets.audit import (
    AssetAuditAdjustment,
    AssetAuditAdjustmentType,
    AssetAuditDiscrepancy,
    AssetAuditLine,
    AssetAuditLineStatus,
    AssetAuditPlan,
    AssetAuditPlanStatus,
    AssetLifecycleEvent,
)
from app.services.common import NotFoundError, PaginatedResult, PaginationParams, ValidationError

__all__ = ["AssetAuditService"]

try:
    from datetime import UTC  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    UTC = timezone.utc


class AssetAuditService:
    """Manage audit plans, checks, discrepancies, and adjustments."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _get_plan(self, org_id: UUID, audit_plan_id: UUID) -> AssetAuditPlan:
        plan = self.db.get(AssetAuditPlan, audit_plan_id)
        if not plan or plan.organization_id != org_id:
            raise NotFoundError("Audit plan not found")
        return plan

    def _get_line(self, org_id: UUID, audit_line_id: UUID) -> AssetAuditLine:
        line = self.db.get(AssetAuditLine, audit_line_id)
        if not line or line.organization_id != org_id:
            raise NotFoundError("Audit line not found")
        return line

    def _get_discrepancy(
        self,
        org_id: UUID,
        audit_line_id: UUID,
        status: str | None = None,
    ) -> AssetAuditDiscrepancy | None:
        query = select(AssetAuditDiscrepancy).where(
            AssetAuditDiscrepancy.organization_id == org_id,
            AssetAuditDiscrepancy.audit_line_id == audit_line_id,
        )
        if status is not None:
            query = query.where(AssetAuditDiscrepancy.status == status)
        return self.db.scalar(query.order_by(AssetAuditDiscrepancy.detected_at.asc()).limit(1))

    def _next_plan_number(self, org_id: UUID) -> str:
        total = self.db.scalar(
            select(func.count(AssetAuditPlan.audit_plan_id)).where(
                AssetAuditPlan.organization_id == org_id
            )
        ) or 0
        return f"FAAUD-{int(total) + 1:06d}"

    def _collect_discrepancy_payload(
        self,
        *,
        line: AssetAuditLine,
        is_found: bool,
        observed_location_id: UUID | None,
        observed_custodian_employee_id: UUID | None,
        observed_status: str | None,
    ) -> tuple[str | None, dict[str, Any], dict[str, Any]]:
        if not is_found:
            return (
                "MISSING",
                {
                    "is_found": True,
                    "expected_location_id": str(line.expected_location_id)
                    if line.expected_location_id
                    else None,
                    "expected_custodian_employee_id": str(
                        line.expected_custodian_employee_id
                    )
                    if line.expected_custodian_employee_id
                    else None,
                    "expected_status": line.expected_status,
                },
                {
                    "is_found": False,
                    "observed_location_id": None,
                    "observed_custodian_employee_id": None,
                    "observed_status": None,
                },
            )

        mismatch_types: list[str] = []
        expected_state: dict[str, Any] = {}
        observed_state: dict[str, Any] = {}

        if (
            line.expected_location_id is not None
            or observed_location_id is not None
        ) and line.expected_location_id != observed_location_id:
            mismatch_types.append("LOCATION")
            expected_state["location_id"] = (
                str(line.expected_location_id) if line.expected_location_id else None
            )
            observed_state["location_id"] = (
                str(observed_location_id) if observed_location_id else None
            )

        if (
            line.expected_custodian_employee_id is not None
            or observed_custodian_employee_id is not None
        ) and line.expected_custodian_employee_id != observed_custodian_employee_id:
            mismatch_types.append("OWNERSHIP")
            expected_state["custodian_employee_id"] = (
                str(line.expected_custodian_employee_id)
                if line.expected_custodian_employee_id
                else None
            )
            observed_state["custodian_employee_id"] = (
                str(observed_custodian_employee_id)
                if observed_custodian_employee_id
                else None
            )

        if (line.expected_status is not None or observed_status is not None) and (
            line.expected_status != observed_status
        ):
            mismatch_types.append("STATE")
            expected_state["status"] = line.expected_status
            observed_state["status"] = observed_status

        if not mismatch_types:
            return None, {}, {}

        if len(mismatch_types) == 1:
            discrepancy_type = mismatch_types[0]
        else:
            discrepancy_type = "MULTI"

        return discrepancy_type, expected_state, observed_state

    def _upsert_discrepancy(
        self,
        *,
        org_id: UUID,
        plan_id: UUID,
        line: AssetAuditLine,
        discrepancy_type: str,
        expected_state: dict[str, Any],
        observed_state: dict[str, Any],
        detected_by_user_id: UUID | None,
        notes: str | None,
    ) -> AssetAuditDiscrepancy:
        discrepancy = self._get_discrepancy(org_id=org_id, audit_line_id=line.audit_line_id, status="OPEN")

        if discrepancy is None:
            discrepancy = AssetAuditDiscrepancy(
                organization_id=org_id,
                audit_plan_id=plan_id,
                audit_line_id=line.audit_line_id,
                asset_id=line.asset_id,
                discrepancy_type=discrepancy_type,
                status="OPEN",
                expected_state=expected_state or None,
                observed_state=observed_state or None,
                notes=notes,
                detected_by_user_id=detected_by_user_id,
            )
            self.db.add(discrepancy)
            return discrepancy

        discrepancy.discrepancy_type = discrepancy_type
        discrepancy.expected_state = expected_state or None
        discrepancy.observed_state = observed_state or None
        discrepancy.notes = notes or discrepancy.notes
        discrepancy.status = "OPEN"
        discrepancy.detected_by_user_id = discrepancy.detected_by_user_id or detected_by_user_id
        discrepancy.resolved_at = None
        discrepancy.resolved_by_user_id = None
        discrepancy.resolution_notes = None
        return discrepancy

    def _resolve_discrepancy(
        self,
        discrepancy: AssetAuditDiscrepancy,
        resolved_by_user_id: UUID | None,
        resolution_notes: str | None,
    ) -> None:
        discrepancy.status = "RESOLVED"
        discrepancy.resolved_by_user_id = resolved_by_user_id
        discrepancy.resolved_at = datetime.now(UTC)
        discrepancy.resolution_notes = resolution_notes

    def list_plans(
        self,
        org_id: UUID,
        *,
        status: AssetAuditPlanStatus | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[AssetAuditPlan]:
        query = select(AssetAuditPlan).where(AssetAuditPlan.organization_id == org_id)
        if status:
            query = query.where(AssetAuditPlan.status == status)
        query = query.order_by(AssetAuditPlan.planned_date.desc())
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

    def create_plan(
        self,
        org_id: UUID,
        *,
        title: str,
        planned_date: date,
        scope_location_id: UUID | None = None,
        asset_ids: list[UUID] | None = None,
        created_by_user_id: UUID | None = None,
    ) -> AssetAuditPlan:
        plan = AssetAuditPlan(
            organization_id=org_id,
            plan_number=self._next_plan_number(org_id),
            title=title,
            planned_date=planned_date,
            scope_location_id=scope_location_id,
            status=AssetAuditPlanStatus.DRAFT,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(plan)
        self.db.flush()

        asset_query = select(Asset).where(Asset.organization_id == org_id)
        if scope_location_id:
            asset_query = asset_query.where(Asset.location_id == scope_location_id)
        if asset_ids:
            asset_query = asset_query.where(Asset.asset_id.in_(asset_ids))
        assets = list(self.db.scalars(asset_query).all())

        for asset in assets:
            self.db.add(
                AssetAuditLine(
                    organization_id=org_id,
                    audit_plan_id=plan.audit_plan_id,
                    asset_id=asset.asset_id,
                    expected_location_id=asset.location_id,
                    expected_custodian_employee_id=asset.custodian_employee_id,
                    expected_status=asset.status.value if asset.status else None,
                    status=AssetAuditLineStatus.PENDING,
                )
            )
        plan.total_assets = len(assets)
        self.db.flush()
        return plan

    def list_lines(
        self,
        org_id: UUID,
        audit_plan_id: UUID,
        *,
        status: AssetAuditLineStatus | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[AssetAuditLine]:
        _ = self._get_plan(org_id, audit_plan_id)
        query = select(AssetAuditLine).where(
            AssetAuditLine.organization_id == org_id,
            AssetAuditLine.audit_plan_id == audit_plan_id,
        )
        if status:
            query = query.where(AssetAuditLine.status == status)
        query = query.order_by(AssetAuditLine.created_at.asc())
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

    def list_discrepancies(
        self,
        org_id: UUID,
        audit_plan_id: UUID,
        *,
        status: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[AssetAuditDiscrepancy]:
        _ = self._get_plan(org_id, audit_plan_id)
        query = select(AssetAuditDiscrepancy).where(
            AssetAuditDiscrepancy.organization_id == org_id,
            AssetAuditDiscrepancy.audit_plan_id == audit_plan_id,
        )
        if status:
            query = query.where(AssetAuditDiscrepancy.status == status)
        query = query.order_by(AssetAuditDiscrepancy.detected_at.asc())
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

    def list_lifecycle_events(
        self,
        org_id: UUID,
        *,
        asset_id: UUID | None = None,
        event_category: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[AssetLifecycleEvent]:
        query = select(AssetLifecycleEvent).where(
            AssetLifecycleEvent.organization_id == org_id,
        )
        if asset_id:
            query = query.where(AssetLifecycleEvent.asset_id == asset_id)
        if event_category:
            query = query.where(AssetLifecycleEvent.event_category == event_category)
        query = query.order_by(AssetLifecycleEvent.event_at.desc())
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

    def start_plan(
        self,
        org_id: UUID,
        audit_plan_id: UUID,
    ) -> AssetAuditPlan:
        plan = self._get_plan(org_id, audit_plan_id)
        if plan.status not in {AssetAuditPlanStatus.DRAFT, AssetAuditPlanStatus.CANCELLED}:
            raise ValidationError(f"Cannot start plan in {plan.status.value} status")
        plan.status = AssetAuditPlanStatus.IN_PROGRESS
        plan.started_at = datetime.now(UTC)
        self.db.flush()
        return plan

    def record_check(
        self,
        org_id: UUID,
        audit_line_id: UUID,
        *,
        is_found: bool,
        observed_location_id: UUID | None = None,
        observed_custodian_employee_id: UUID | None = None,
        observed_status: str | None = None,
        discrepancy_notes: str | None = None,
        checked_by_user_id: UUID | None = None,
    ) -> AssetAuditLine:
        line = self._get_line(org_id, audit_line_id)

        line.is_found = is_found
        line.observed_location_id = observed_location_id
        line.observed_custodian_employee_id = observed_custodian_employee_id
        line.observed_status = observed_status
        line.discrepancy_notes = discrepancy_notes
        line.checked_by_user_id = checked_by_user_id
        line.physical_check_at = datetime.now(UTC)

        discrepancy_type, expected_state, observed_state = self._collect_discrepancy_payload(
            line=line,
            is_found=is_found,
            observed_location_id=observed_location_id,
            observed_custodian_employee_id=observed_custodian_employee_id,
            observed_status=observed_status,
        )

        if discrepancy_type is None:
            line.status = AssetAuditLineStatus.FOUND
            current_discrepancy = self._get_discrepancy(
                org_id=org_id,
                audit_line_id=line.audit_line_id,
                status="OPEN",
            )
            if current_discrepancy:
                self._resolve_discrepancy(
                    current_discrepancy,
                    resolved_by_user_id=checked_by_user_id,
                    resolution_notes="Resolved by physical check",
                )
        else:
            if discrepancy_type == "MISSING":
                line.status = AssetAuditLineStatus.MISSING
            else:
                line.status = AssetAuditLineStatus.DISCREPANCY
            self._upsert_discrepancy(
                org_id=org_id,
                plan_id=line.audit_plan_id,
                line=line,
                discrepancy_type=discrepancy_type,
                expected_state=expected_state,
                observed_state=observed_state,
                detected_by_user_id=checked_by_user_id,
                notes=discrepancy_notes,
            )

        self.db.flush()
        return line

    def complete_plan(self, org_id: UUID, audit_plan_id: UUID) -> AssetAuditPlan:
        plan = self._get_plan(org_id, audit_plan_id)
        lines = list(
            self.db.scalars(
                select(AssetAuditLine).where(
                    AssetAuditLine.organization_id == org_id,
                    AssetAuditLine.audit_plan_id == audit_plan_id,
                )
            ).all()
        )
        plan.found_count = len(
            [line for line in lines if line.status == AssetAuditLineStatus.FOUND]
        )
        plan.missing_count = len(
            [line for line in lines if line.status == AssetAuditLineStatus.MISSING]
        )
        plan.discrepancy_count = len(
            [line for line in lines if line.status == AssetAuditLineStatus.DISCREPANCY]
        )
        plan.completed_at = datetime.now(UTC)
        plan.status = AssetAuditPlanStatus.COMPLETED
        self.db.flush()
        return plan

    def _mark_plan_adjusted_if_needed(
        self,
        line: AssetAuditLine,
    ) -> None:
        plan = self._get_plan(line.organization_id, line.audit_plan_id)
        if plan.status == AssetAuditPlanStatus.COMPLETED:
            plan.status = AssetAuditPlanStatus.ADJUSTED

    def apply_adjustment(
        self,
        org_id: UUID,
        audit_line_id: UUID,
        *,
        adjustment_type: AssetAuditAdjustmentType,
        new_value: str | None = None,
        notes: str | None = None,
        applied_by_user_id: UUID | None = None,
    ) -> AssetAuditAdjustment:
        line = self._get_line(org_id, audit_line_id)
        plan = self._get_plan(org_id, line.audit_plan_id)
        asset = self.db.get(Asset, line.asset_id)
        if not asset or asset.organization_id != org_id:
            raise NotFoundError("Asset not found")

        previous_value: str | None = None

        if adjustment_type == AssetAuditAdjustmentType.UPDATE_LOCATION:
            if not new_value:
                raise ValidationError("new_value is required for UPDATE_LOCATION")
            previous_value = str(asset.location_id) if asset.location_id else None
            asset.location_id = UUID(new_value)
            line.expected_location_id = asset.location_id
        elif adjustment_type == AssetAuditAdjustmentType.UPDATE_CUSTODIAN:
            previous_value = (
                str(asset.custodian_employee_id)
                if asset.custodian_employee_id
                else None
            )
            asset.custodian_employee_id = UUID(new_value) if new_value else None
            line.expected_custodian_employee_id = asset.custodian_employee_id
        elif adjustment_type == AssetAuditAdjustmentType.UPDATE_STATUS:
            previous_value = asset.status.value
            if not new_value:
                raise ValidationError("new_value is required for UPDATE_STATUS")
            asset.status = AssetStatus(new_value)
            line.expected_status = new_value
        elif adjustment_type == AssetAuditAdjustmentType.MARK_FOUND:
            previous_value = str(line.is_found)
            line.is_found = True
            line.status = AssetAuditLineStatus.RESOLVED
        elif adjustment_type == AssetAuditAdjustmentType.MARK_MISSING:
            previous_value = str(line.is_found)
            line.is_found = False
            line.status = AssetAuditLineStatus.RESOLVED

        discrepancy = self._get_discrepancy(
            org_id=org_id,
            audit_line_id=line.audit_line_id,
            status="OPEN",
        )
        if discrepancy is not None:
            self._resolve_discrepancy(
                discrepancy,
                resolved_by_user_id=applied_by_user_id,
                resolution_notes=notes,
            )

        adjustment = AssetAuditAdjustment(
            organization_id=org_id,
            audit_plan_id=plan.audit_plan_id,
            audit_line_id=line.audit_line_id,
            asset_id=line.asset_id,
            adjustment_type=adjustment_type,
            previous_value=previous_value,
            new_value=new_value,
            notes=notes,
            applied_by_user_id=applied_by_user_id,
        )
        self.db.add(adjustment)

        if line.status == AssetAuditLineStatus.DISCREPANCY:
            line.status = AssetAuditLineStatus.RESOLVED
        self._mark_plan_adjusted_if_needed(line)
        self.db.flush()
        return adjustment

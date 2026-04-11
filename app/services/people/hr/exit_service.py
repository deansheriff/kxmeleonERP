"""
Exit Workflow Service — Core business logic for exit interviews and clearance.

Handles:
- Exit interview creation, completion, and skipping
- Standard clearance checklist generation
- Clearance item tracking and status aggregation
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.people.hr.clearance_checklist import (
    ClearanceCategory,
    ClearanceItem,
)
from app.models.people.hr.exit_interview import (
    ExitInterview,
    InterviewStatus,
    OverallExperience,
    ReasonForLeaving,
)

logger = logging.getLogger(__name__)

# Standard clearance items created for every separation
STANDARD_CLEARANCE_ITEMS: list[tuple[ClearanceCategory, str]] = [
    (ClearanceCategory.IT_ACCESS, "Revoke all IT access, email, and system accounts"),
    (ClearanceCategory.EQUIPMENT, "Return all company equipment (laptop, phone, keys)"),
    (ClearanceCategory.HR_DOCUMENTS, "Return company ID card and access badges"),
    (ClearanceCategory.FINANCE, "Settle all financial obligations and advances"),
    (
        ClearanceCategory.KNOWLEDGE_TRANSFER,
        "Complete knowledge transfer and handover documentation",
    ),
    (
        ClearanceCategory.OTHER,
        "Return all company documents and confidential materials",
    ),
]


class ExitService:
    """Service for managing exit interviews and clearance checklists."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # =========================================================================
    # Exit Interview — Read
    # =========================================================================

    def get_exit_interview(
        self,
        organization_id: UUID,
        interview_id: UUID,
    ) -> ExitInterview | None:
        """Get exit interview by ID, scoped to organization."""
        interview = self.db.get(ExitInterview, interview_id)
        if interview and interview.organization_id != organization_id:
            return None
        return interview

    def get_exit_interview_by_separation(
        self,
        organization_id: UUID,
        separation_id: UUID,
    ) -> ExitInterview | None:
        """Get exit interview for a given separation."""
        stmt = select(ExitInterview).where(
            ExitInterview.organization_id == organization_id,
            ExitInterview.separation_id == separation_id,
        )
        return self.db.scalar(stmt)

    # =========================================================================
    # Exit Interview — Write
    # =========================================================================

    def create_exit_interview(
        self,
        organization_id: UUID,
        separation_id: UUID,
        employee_id: UUID,
    ) -> ExitInterview:
        """Create a new exit interview in PENDING status."""
        # Check for existing interview for this separation
        existing = self.get_exit_interview_by_separation(organization_id, separation_id)
        if existing:
            raise ValueError(
                f"Exit interview already exists for separation {separation_id}"
            )

        interview = ExitInterview(
            organization_id=organization_id,
            separation_id=separation_id,
            employee_id=employee_id,
            status=InterviewStatus.PENDING,
        )
        self.db.add(interview)
        self.db.flush()

        logger.info(
            "Created exit interview %s for separation %s",
            interview.interview_id,
            separation_id,
        )
        return interview

    def complete_exit_interview(
        self,
        organization_id: UUID,
        interview_id: UUID,
        data: dict[str, str | bool | None],
    ) -> ExitInterview:
        """Complete an exit interview with structured feedback data."""
        interview = self._get_interview_or_raise(organization_id, interview_id)

        if interview.status not in (
            InterviewStatus.PENDING,
            InterviewStatus.SCHEDULED,
        ):
            raise ValueError(
                f"Cannot complete interview in {interview.status.value} status"
            )

        # Map known fields
        if "interview_date" in data:
            val = data["interview_date"]
            if isinstance(val, str):
                interview.interview_date = date.fromisoformat(val)
            elif isinstance(val, date):
                interview.interview_date = val
        else:
            interview.interview_date = date.today()

        if "overall_experience" in data and data["overall_experience"]:
            interview.overall_experience = OverallExperience(
                str(data["overall_experience"])
            )
        if "reason_for_leaving" in data and data["reason_for_leaving"]:
            interview.reason_for_leaving = ReasonForLeaving(
                str(data["reason_for_leaving"])
            )

        if "would_recommend" in data:
            interview.would_recommend = bool(data["would_recommend"])
        if "would_return" in data:
            interview.would_return = bool(data["would_return"])

        # Free-text fields
        for field_name in (
            "likes_about_company",
            "dislikes_about_company",
            "suggestions",
            "management_feedback",
            "additional_comments",
        ):
            if field_name in data:
                setattr(interview, field_name, data[field_name])

        if "conducted_by_id" in data and data["conducted_by_id"]:
            interview.conducted_by_id = UUID(str(data["conducted_by_id"]))

        interview.status = InterviewStatus.COMPLETED
        self.db.flush()

        logger.info("Completed exit interview %s", interview.interview_id)
        return interview

    def skip_exit_interview(
        self,
        organization_id: UUID,
        interview_id: UUID,
    ) -> ExitInterview:
        """Mark exit interview as skipped."""
        interview = self._get_interview_or_raise(organization_id, interview_id)

        if interview.status not in (
            InterviewStatus.PENDING,
            InterviewStatus.SCHEDULED,
        ):
            raise ValueError(
                f"Cannot skip interview in {interview.status.value} status"
            )

        interview.status = InterviewStatus.SKIPPED
        self.db.flush()

        logger.info("Skipped exit interview %s", interview.interview_id)
        return interview

    # =========================================================================
    # Clearance Checklist — Read
    # =========================================================================

    def get_clearance_items(
        self,
        organization_id: UUID,
        separation_id: UUID,
    ) -> list[ClearanceItem]:
        """Get all clearance items for a separation, ordered by sort_order."""
        stmt = (
            select(ClearanceItem)
            .where(
                ClearanceItem.organization_id == organization_id,
                ClearanceItem.separation_id == separation_id,
            )
            .order_by(ClearanceItem.sort_order.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_clearance_status(
        self,
        organization_id: UUID,
        separation_id: UUID,
    ) -> dict[str, int]:
        """Get clearance status summary: {total, cleared, pending}."""
        stmt = select(
            func.count().label("total"),
            func.count().filter(ClearanceItem.is_cleared.is_(True)).label("cleared"),
        ).where(
            ClearanceItem.organization_id == organization_id,
            ClearanceItem.separation_id == separation_id,
        )
        row = self.db.execute(stmt).one()
        total = row.total or 0
        cleared = row.cleared or 0

        return {
            "total": total,
            "cleared": cleared,
            "pending": total - cleared,
        }

    def is_fully_cleared(
        self,
        organization_id: UUID,
        separation_id: UUID,
    ) -> bool:
        """Check if all clearance items are cleared for a separation."""
        status = self.get_clearance_status(organization_id, separation_id)
        return status["total"] > 0 and status["pending"] == 0

    # =========================================================================
    # Clearance Checklist — Write
    # =========================================================================

    def create_clearance_checklist(
        self,
        organization_id: UUID,
        separation_id: UUID,
    ) -> list[ClearanceItem]:
        """Create standard clearance checklist items for a separation.

        Creates 6 standard items covering IT, Equipment, ID Card,
        Finance, Knowledge Transfer, and Document Handover.
        """
        # Check if checklist already exists
        existing = self.get_clearance_items(organization_id, separation_id)
        if existing:
            raise ValueError(
                f"Clearance checklist already exists for separation {separation_id}"
            )

        items: list[ClearanceItem] = []
        for idx, (category, description) in enumerate(STANDARD_CLEARANCE_ITEMS):
            item = ClearanceItem(
                organization_id=organization_id,
                separation_id=separation_id,
                category=category,
                description=description,
                sort_order=idx + 1,
                is_cleared=False,
            )
            self.db.add(item)
            items.append(item)

        self.db.flush()

        logger.info(
            "Created %d clearance items for separation %s",
            len(items),
            separation_id,
        )
        return items

    def clear_item(
        self,
        organization_id: UUID,
        item_id: UUID,
        cleared_by_id: UUID,
    ) -> ClearanceItem:
        """Mark a clearance item as cleared."""
        item = self.db.get(ClearanceItem, item_id)
        if not item or item.organization_id != organization_id:
            raise ValueError(f"Clearance item {item_id} not found")

        if item.is_cleared:
            raise ValueError(f"Clearance item {item_id} is already cleared")

        item.is_cleared = True
        item.cleared_by_id = cleared_by_id
        item.cleared_at = datetime.now(timezone.utc)
        self.db.flush()

        logger.info("Cleared item %s by %s", item.item_id, cleared_by_id)
        return item

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_interview_or_raise(
        self,
        organization_id: UUID,
        interview_id: UUID,
    ) -> ExitInterview:
        """Get exit interview or raise ValueError."""
        interview = self.get_exit_interview(organization_id, interview_id)
        if not interview:
            raise ValueError(f"Exit interview {interview_id} not found")
        return interview

"""
AppraisalAppeal Model - Performance Schema.

Tracks employee appeals against appraisal outcomes, including mediation
and committee review stages.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.people.base import AuditMixin
from app.models.people.perf.pms_enums import AppealDecision, AppealStatus

if TYPE_CHECKING:
    from app.models.people.hr.employee import Employee
    from app.models.people.perf.appraisal import Appraisal


class AppraisalAppeal(Base, AuditMixin):
    """
    AppraisalAppeal — an employee's formal challenge to an appraisal outcome.

    Covers the full appeal lifecycle: filing, mediation, committee referral,
    decision, resolution, and communication to the employee.
    """

    __tablename__ = "appraisal_appeal"
    __table_args__ = (
        Index("idx_appeal_appraisal", "appraisal_id"),
        Index("idx_appeal_org_status", "organization_id", "status"),
        {"schema": "perf"},
    )

    # Primary key
    appeal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Multi-tenancy
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core_org.organization.organization_id"),
        nullable=False,
        index=True,
    )

    # Core links
    appraisal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perf.appraisal.appraisal_id"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )

    # Appeal filing
    status: Mapped[AppealStatus] = mapped_column(
        Enum(AppealStatus, name="appeal_status", schema="perf"),
        nullable=False,
        default=AppealStatus.FILED,
    )
    filed_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    requested_outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Mediation stage
    mediator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=True,
    )
    mediation_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    mediation_outcome: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    mediation_resolved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Committee stage
    committee_referral_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    committee_hearing_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    committee_decision: Mapped[AppealDecision | None] = mapped_column(
        Enum(AppealDecision, name="appeal_decision", schema="perf"),
        nullable=True,
    )
    committee_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    adjusted_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Final adjusted rating granted by committee (1-5)",
    )

    # Resolution
    resolution_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    resolution_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    communicated_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Date outcome was formally communicated to employee",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    appraisal: Mapped["Appraisal"] = relationship(
        "Appraisal",
        foreign_keys=[appraisal_id],
    )
    employee: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[employee_id],
    )
    mediator: Mapped[Optional["Employee"]] = relationship(
        "Employee",
        foreign_keys=[mediator_id],
    )

    def __repr__(self) -> str:
        return f"<AppraisalAppeal {self.appeal_id}>"

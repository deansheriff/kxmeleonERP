"""
Performance Improvement Plan Model - OHCSF Performance Management System.

Represents a formal performance improvement plan issued to an employee
who has failed to meet performance standards. Tracks cause analysis,
improvement targets, support measures, review intervals, and outcomes.
Supports extension tracking and escalation to a disciplinary committee.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.people.base import AuditMixin
from app.models.people.perf.pms_enums import PIPCauseCategory, PIPOutcome, PIPStatus

if TYPE_CHECKING:
    from app.models.people.hr.employee import Employee
    from app.models.people.perf.appraisal import Appraisal


class PerformanceImprovementPlan(Base, AuditMixin):
    """
    Performance Improvement Plan (PIP) - formal remediation plan for an employee.

    Links an employee to a structured set of improvement areas, timelines,
    and support measures. Tracks the full lifecycle from draft through
    outcome (satisfactory/unsatisfactory) or escalation to committee.
    """

    __tablename__ = "performance_improvement_plan"
    __table_args__ = (
        UniqueConstraint("organization_id", "pip_code", name="uq_pip_code"),
        Index("idx_pip_employee", "employee_id"),
        Index("idx_pip_org_status", "organization_id", "status"),
        {"schema": "perf"},
    )

    pip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core_org.organization.organization_id"),
        nullable=False,
        index=True,
    )

    # Parties
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )
    supervisor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )
    hr_officer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )

    # Optional link to the appraisal that triggered the PIP
    appraisal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perf.appraisal.appraisal_id"),
        nullable=True,
    )

    # Identification
    pip_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # Status & Lifecycle
    status: Mapped[PIPStatus] = mapped_column(
        Enum(PIPStatus, name="pip_status", schema="perf"),
        nullable=False,
        default=PIPStatus.DRAFT,
    )
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    # Cause Analysis
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Narrative reason for initiating the PIP",
    )
    cause_category: Mapped[PIPCauseCategory] = mapped_column(
        Enum(PIPCauseCategory, name="pip_cause_category", schema="perf"),
        nullable=False,
    )

    # Improvement Plan Content
    improvement_areas: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="List of dicts describing each improvement area and its target",
    )
    support_measures: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Training, coaching, or other support provided",
    )
    review_intervals: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Scheduled check-in/review points during the PIP period",
    )

    # Extension
    extension_granted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    extension_end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    extension_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Outcome
    outcome: Mapped[PIPOutcome | None] = mapped_column(
        Enum(PIPOutcome, name="pip_outcome", schema="perf"),
        nullable=True,
    )
    outcome_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    outcome_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    completion_letter_issued: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # Escalation / Committee
    escalation_action: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="E.g. DISCIPLINARY, DEMOTION, TERMINATION",
    )
    committee_referral_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    committee_decision: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
    employee: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[employee_id],
    )
    supervisor: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[supervisor_id],
    )
    hr_officer: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[hr_officer_id],
    )
    appraisal: Mapped[Optional["Appraisal"]] = relationship("Appraisal")

    def __repr__(self) -> str:
        return f"<PerformanceImprovementPlan {self.pip_code}: {self.status}>"

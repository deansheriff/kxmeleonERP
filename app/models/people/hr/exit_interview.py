"""
Exit Interview Model - HR Schema.

Captures structured feedback from departing employees during the
offboarding/separation process.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from datetime import date as date_type

    from app.models.finance.core_org.organization import Organization
    from app.models.people.hr.employee import Employee
    from app.models.people.hr.lifecycle import EmployeeSeparation


class OverallExperience(str, enum.Enum):
    """Overall experience rating."""

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class ReasonForLeaving(str, enum.Enum):
    """Structured reason for leaving the organization."""

    BETTER_OPPORTUNITY = "BETTER_OPPORTUNITY"
    COMPENSATION = "COMPENSATION"
    MANAGEMENT = "MANAGEMENT"
    CULTURE = "CULTURE"
    PERSONAL = "PERSONAL"
    RELOCATION = "RELOCATION"
    CAREER_GROWTH = "CAREER_GROWTH"
    WORK_LIFE_BALANCE = "WORK_LIFE_BALANCE"
    OTHER = "OTHER"


class InterviewStatus(str, enum.Enum):
    """Status of the exit interview."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class ExitInterview(Base):
    """
    Exit interview record.

    One-to-one with EmployeeSeparation. Captures structured and
    free-text feedback from the departing employee.
    """

    __tablename__ = "exit_interview"
    __table_args__ = (
        UniqueConstraint(
            "separation_id",
            name="uq_exit_interview_separation",
        ),
        Index("idx_exit_interview_org", "organization_id"),
        Index("idx_exit_interview_employee", "organization_id", "employee_id"),
        {"schema": "hr"},
    )

    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core_org.organization.organization_id"),
        nullable=False,
    )
    separation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee_separation.separation_id"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )
    conducted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=True,
        comment="HR officer who conducted the interview",
    )

    # Interview details
    interview_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    overall_experience: Mapped[OverallExperience | None] = mapped_column(
        Enum(OverallExperience, name="hr_overall_experience"),
        nullable=True,
    )
    reason_for_leaving: Mapped[ReasonForLeaving | None] = mapped_column(
        Enum(ReasonForLeaving, name="hr_reason_for_leaving"),
        nullable=True,
    )

    # Boolean responses
    would_recommend: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    would_return: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Free-text feedback
    likes_about_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    dislikes_about_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[InterviewStatus] = mapped_column(
        Enum(InterviewStatus, name="hr_interview_status"),
        nullable=False,
        default=InterviewStatus.PENDING,
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
    organization: Mapped[Organization | None] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )
    separation: Mapped[EmployeeSeparation | None] = relationship(
        "EmployeeSeparation",
        foreign_keys=[separation_id],
    )
    employee: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys=[employee_id],
    )
    conducted_by: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys=[conducted_by_id],
    )

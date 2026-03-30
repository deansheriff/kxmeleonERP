"""
Monthly Review Model - OHCSF Performance Management System.

Represents a monthly performance check-in between an employee and their
reviewer, tracking objective progress, challenges, agreed actions, and
sign-off dates against an active performance contract.
"""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
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
from app.models.people.base import AuditMixin
from app.models.people.perf.pms_enums import MonthlyReviewStatus

if TYPE_CHECKING:
    from app.models.people.hr.employee import Employee
    from app.models.people.perf.performance_contract import PerformanceContract


class MonthlyReview(Base, AuditMixin):
    """
    Monthly performance review between an employee and their reviewer.

    Each employee/contract pair may have at most one review per calendar
    month (enforced by the unique constraint on organization_id + employee_id
    + review_month).
    """

    __tablename__ = "monthly_review"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "employee_id",
            "review_month",
            name="uq_monthly_review",
        ),
        Index("idx_review_employee", "employee_id"),
        Index("idx_review_month", "organization_id", "review_month"),
        {"schema": "perf"},
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
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
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=False,
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perf.performance_contract.contract_id"),
        nullable=False,
    )

    # Review period
    review_month: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="First day of the review month (e.g. 2026-03-01)",
    )

    # Workflow status
    status: Mapped[MonthlyReviewStatus] = mapped_column(
        Enum(MonthlyReviewStatus, name="monthly_review_status", schema="perf"),
        nullable=False,
        default=MonthlyReviewStatus.DRAFT,
    )

    # Review content
    objective_progress: Mapped[dict | list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Progress update per KRA/KPI objective",
    )
    challenges: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    support_required: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    reviewer_feedback: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    agreed_actions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Sign-off dates
    employee_signed_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    reviewer_signed_date: Mapped[date | None] = mapped_column(
        Date,
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
    reviewer: Mapped["Employee"] = relationship(
        "Employee",
        foreign_keys=[reviewer_id],
    )
    contract: Mapped["PerformanceContract"] = relationship(
        "PerformanceContract",
        foreign_keys=[contract_id],
    )

    def __repr__(self) -> str:
        return f"<MonthlyReview {self.review_month}: {self.status}>"

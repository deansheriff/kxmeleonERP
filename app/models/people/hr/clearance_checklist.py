"""
Clearance Checklist Model - HR Schema.

Tracks individual clearance items for employee offboarding/separation.
Each item represents a task that must be completed before the employee
is fully cleared to leave the organization.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.finance.core_org.organization import Organization
    from app.models.people.hr.lifecycle import EmployeeSeparation


class ClearanceCategory(str, enum.Enum):
    """Category of clearance item."""

    IT_ACCESS = "IT_ACCESS"
    EQUIPMENT = "EQUIPMENT"
    FINANCE = "FINANCE"
    HR_DOCUMENTS = "HR_DOCUMENTS"
    KNOWLEDGE_TRANSFER = "KNOWLEDGE_TRANSFER"
    OTHER = "OTHER"


class ClearanceItem(Base):
    """
    Individual clearance checklist item for an employee separation.

    Each item is assigned to a department head or responsible person
    and must be marked as cleared before the separation is considered
    fully complete.
    """

    __tablename__ = "clearance_item"
    __table_args__ = (
        Index("idx_clearance_org_separation", "organization_id", "separation_id"),
        Index("idx_clearance_is_cleared", "separation_id", "is_cleared"),
        {"schema": "hr"},
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
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

    # Item details
    category: Mapped[ClearanceCategory] = mapped_column(
        Enum(ClearanceCategory, name="hr_clearance_category"),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=True,
        comment="Department head responsible for clearing this item",
    )

    # Clearance tracking
    is_cleared: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    cleared_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
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

"""
Employment Contract Model - HR Schema.

Tracks employee employment contracts, renewals, and terminations.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
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

    from app.models.finance.automation.document_template import DocumentTemplate
    from app.models.finance.automation.generated_document import GeneratedDocument
    from app.models.finance.core_org.organization import Organization
    from app.models.people.hr.employee import Employee


class ContractType(str, enum.Enum):
    """Type of employment contract."""

    PERMANENT = "PERMANENT"
    FIXED_TERM = "FIXED_TERM"
    PROBATION = "PROBATION"
    INTERNSHIP = "INTERNSHIP"
    CASUAL = "CASUAL"
    CONSULTANT = "CONSULTANT"


class ContractStatus(str, enum.Enum):
    """Status of an employment contract."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    RENEWED = "RENEWED"
    TERMINATED = "TERMINATED"


class EmploymentContract(Base):
    """
    Employment contract record.

    Tracks the lifecycle of an employee's contract including type,
    dates, salary terms, renewals, and document generation.
    """

    __tablename__ = "employment_contract"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "contract_number",
            name="uq_employment_contract_org_number",
        ),
        Index("idx_contract_org_employee", "organization_id", "employee_id"),
        Index("idx_contract_org_status", "organization_id", "status"),
        Index("idx_contract_end_date", "end_date", "status"),
        {"schema": "hr"},
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
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

    # Identification
    contract_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Unique contract number, e.g. CT-2026-0001",
    )
    contract_type: Mapped[ContractType] = mapped_column(
        Enum(ContractType, name="hr_contract_type"),
        nullable=False,
    )

    # Dates
    start_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    end_date: Mapped[date_type | None] = mapped_column(
        Date,
        nullable=True,
        comment="Null for permanent contracts",
    )
    probation_end_date: Mapped[date_type | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Terms
    terms: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Summary of contract terms",
    )
    salary_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 6),
        nullable=True,
    )
    currency_code: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="NGN",
    )
    notice_period_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )
    working_hours_per_week: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    # Renewal chain
    previous_contract_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employment_contract.contract_id"),
        nullable=True,
        comment="Previous contract this one renews",
    )
    renewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employment_contract.contract_id"),
        nullable=True,
        comment="New contract that replaced this one",
    )

    # Document generation
    document_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation.document_template.template_id"),
        nullable=True,
    )
    generated_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation.generated_document.document_id"),
        nullable=True,
    )

    # Status
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="hr_contract_status"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    employee: Mapped[Employee | None] = relationship(
        "Employee",
        foreign_keys=[employee_id],
    )
    organization: Mapped[Organization | None] = relationship(
        "Organization",
        foreign_keys=[organization_id],
    )
    previous_contract: Mapped[EmploymentContract | None] = relationship(
        "EmploymentContract",
        remote_side=[contract_id],
        foreign_keys=[previous_contract_id],
    )
    renewed_by: Mapped[EmploymentContract | None] = relationship(
        "EmploymentContract",
        remote_side=[contract_id],
        foreign_keys=[renewed_by_id],
    )
    document_template: Mapped[DocumentTemplate | None] = relationship(
        "DocumentTemplate",
        foreign_keys=[document_template_id],
    )
    generated_document: Mapped[GeneratedDocument | None] = relationship(
        "GeneratedDocument",
        foreign_keys=[generated_document_id],
    )

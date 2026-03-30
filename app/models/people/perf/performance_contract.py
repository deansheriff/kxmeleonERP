"""
Performance Contract Model - OHCSF Performance Management System.

Represents an individual or departmental performance agreement between
an employee and their supervisor within an appraisal cycle. Supports
ministerial, departmental, and individual contract types with amendment
tracking.
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
from app.models.people.perf.pms_enums import ContractStatus, ContractType

if TYPE_CHECKING:
    from app.models.people.hr.employee import Employee
    from app.models.people.perf.appraisal_cycle import AppraisalCycle


class PerformanceContract(Base, AuditMixin):
    """
    Performance Contract - links an employee to a cycle with agreed objectives.

    Supports self-referential amendment chain (amended_from_id) and
    multi-signatory workflow (employee, supervisor, countersigner).
    """

    __tablename__ = "performance_contract"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "contract_code",
            name="uq_perf_contract_code",
        ),
        Index("idx_contract_employee", "employee_id"),
        Index("idx_contract_cycle", "cycle_id"),
        Index("idx_contract_org_status", "organization_id", "status"),
        {"schema": "perf"},
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
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perf.appraisal_cycle.cycle_id"),
        nullable=False,
    )
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

    # Identification
    contract_code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    contract_type: Mapped[ContractType] = mapped_column(
        Enum(ContractType, name="contract_type", schema="perf"),
        nullable=False,
    )
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="contract_status", schema="perf"),
        nullable=False,
        default=ContractStatus.DRAFT,
    )

    # Content
    objectives: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="List of KRA/KPI objective dicts with weights",
    )
    competency_ids: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="List of competency UUIDs linked to this contract",
    )
    development_plan: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Signature tracking
    employee_signed_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    supervisor_signed_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )
    countersigner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr.employee.employee_id"),
        nullable=True,
    )
    countersigner_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Amendment tracking (self-referential)
    amended_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("perf.performance_contract.contract_id"),
        nullable=True,
    )
    amendment_reason: Mapped[str | None] = mapped_column(
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
    countersigner: Mapped["Employee | None"] = relationship(
        "Employee",
        foreign_keys=[countersigner_id],
    )
    cycle: Mapped["AppraisalCycle"] = relationship(
        "AppraisalCycle",
        foreign_keys=[cycle_id],
    )
    amended_from: Mapped["PerformanceContract | None"] = relationship(
        "PerformanceContract",
        foreign_keys=[amended_from_id],
        back_populates="amendments",
        remote_side="PerformanceContract.contract_id",
    )
    amendments: Mapped[list["PerformanceContract"]] = relationship(
        "PerformanceContract",
        foreign_keys=[amended_from_id],
        back_populates="amended_from",
    )

    def __repr__(self) -> str:
        return f"<PerformanceContract {self.contract_code}: {self.status}>"

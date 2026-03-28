"""
Performance Contract Service — OHCSF Performance Management System.

Handles creation, signing workflow, amendment, and querying of
PerformanceContract records within the PMS module.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.people.perf.performance_contract import PerformanceContract
from app.models.people.perf.pms_enums import ContractStatus, ContractType
from app.services.common import PaginatedResult, PaginationParams, paginate

if TYPE_CHECKING:
    from app.web.deps import WebAuthContext

logger = logging.getLogger(__name__)

__all__ = [
    "ContractServiceError",
    "ContractNotFoundError",
    "ContractValidationError",
    "ContractStatusError",
    "PerformanceContractService",
]


# =============================================================================
# Error classes
# =============================================================================


class ContractServiceError(Exception):
    """Base error for PerformanceContractService."""


class ContractNotFoundError(ContractServiceError):
    """Raised when a contract cannot be found."""

    def __init__(self, contract_id: UUID) -> None:
        self.contract_id = contract_id
        super().__init__(f"Performance contract {contract_id} not found")


class ContractValidationError(ContractServiceError):
    """Raised when contract input validation fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ContractStatusError(ContractServiceError):
    """Raised when a status transition is invalid."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition from {current} to {target}")


# =============================================================================
# Service
# =============================================================================


class PerformanceContractService:
    """Service for managing OHCSF performance contracts."""

    def __init__(self, db: Session, ctx: WebAuthContext | None = None) -> None:
        self.db = db
        self.ctx = ctx

    # ------------------------------------------------------------------
    # Private validation helpers
    # ------------------------------------------------------------------

    def _validate_objectives(self, objectives: list[dict]) -> None:
        """Validate performance objectives.

        Rules:
        - Must contain between 3 and 7 objectives (inclusive).
        - The sum of ``weight`` values must equal exactly 70.

        Raises:
            ContractValidationError: if either rule is violated.
        """
        count = len(objectives)
        if count < 3 or count > 7:
            raise ContractValidationError(
                f"Objectives must be between 3 and 7 (got {count})"
            )
        total_weight = sum(int(obj.get("weight", 0)) for obj in objectives)
        if total_weight != 70:
            raise ContractValidationError(
                f"Objective weights must sum to 70 (got {total_weight})"
            )

    def _validate_competency_selections(self, competencies: list[dict]) -> None:
        """Validate competency development-focus selections.

        Rules:
        - Exactly 3 competencies must have ``is_development_focus=True``.

        Raises:
            ContractValidationError: if the rule is violated.
        """
        dev_focus = [c for c in competencies if c.get("is_development_focus")]
        if len(dev_focus) != 3:
            raise ContractValidationError(
                f"Exactly 3 competencies must be marked as development focus "
                f"(got {len(dev_focus)})"
            )

    # ------------------------------------------------------------------
    # Public query methods
    # ------------------------------------------------------------------

    def get_contract(
        self, org_id: UUID, contract_id: UUID
    ) -> PerformanceContract:
        """Return a contract by ID scoped to the organisation.

        Raises:
            ContractNotFoundError: if not found.
        """
        stmt = select(PerformanceContract).where(
            PerformanceContract.organization_id == org_id,
            PerformanceContract.contract_id == contract_id,
        )
        contract = self.db.scalar(stmt)
        if contract is None:
            raise ContractNotFoundError(contract_id)
        return contract

    def list_contracts(
        self,
        org_id: UUID,
        *,
        cycle_id: UUID | None = None,
        employee_id: UUID | None = None,
        status: ContractStatus | None = None,
        search: str | None = None,
        pagination: PaginationParams | None = None,
    ) -> PaginatedResult[PerformanceContract]:
        """List performance contracts for an organisation with optional filters."""
        stmt = (
            select(PerformanceContract)
            .where(PerformanceContract.organization_id == org_id)
            .order_by(PerformanceContract.created_at.desc())
        )

        if cycle_id is not None:
            stmt = stmt.where(PerformanceContract.cycle_id == cycle_id)
        if employee_id is not None:
            stmt = stmt.where(PerformanceContract.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(PerformanceContract.status == status)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                PerformanceContract.contract_code.ilike(pattern)
            )

        return paginate(
            self.db,
            stmt,
            pagination,
            count_column=PerformanceContract.contract_id,
        )

    # ------------------------------------------------------------------
    # Public mutation methods
    # ------------------------------------------------------------------

    def create_contract(
        self,
        org_id: UUID,
        *,
        cycle_id: UUID,
        employee_id: UUID,
        supervisor_id: UUID,
        contract_code: str,
        contract_type: ContractType,
        objectives: list[dict],
        competency_ids: list | None = None,
        development_plan: str | None = None,
    ) -> PerformanceContract:
        """Create a new performance contract.

        Validates objectives and, when provided, competency selections
        before persisting.

        Raises:
            ContractValidationError: if validation fails.
        """
        # Sequencing gate: institutional goals must exist for this cycle/department
        from app.models.people.hr.employee import Employee
        from app.models.people.perf.institutional_performance import InstitutionalPerformance
        from app.models.people.perf.pms_enums import InstitutionalPerfStatus

        employee = self.db.scalar(
            select(Employee).where(Employee.employee_id == employee_id)
        )
        if employee and employee.department_id:
            inst_perf = self.db.scalar(
                select(InstitutionalPerformance).where(
                    InstitutionalPerformance.organization_id == org_id,
                    InstitutionalPerformance.cycle_id == cycle_id,
                    InstitutionalPerformance.department_id == employee.department_id,
                    InstitutionalPerformance.status != InstitutionalPerfStatus.DRAFT,
                )
            )
            if not inst_perf:
                raise ContractValidationError(
                    "Departmental goals must be agreed before individual performance planning. "
                    "Create and approve institutional performance targets for this department first."
                )

        self._validate_objectives(objectives)
        if competency_ids is not None:
            # competency_ids here is a list of dicts with is_development_focus
            if isinstance(competency_ids, list) and competency_ids and isinstance(
                competency_ids[0], dict
            ):
                self._validate_competency_selections(competency_ids)

        contract = PerformanceContract(
            organization_id=org_id,
            cycle_id=cycle_id,
            employee_id=employee_id,
            supervisor_id=supervisor_id,
            contract_code=contract_code,
            contract_type=contract_type,
            objectives=objectives,
            competency_ids=competency_ids,
            development_plan=development_plan,
            status=ContractStatus.DRAFT,
        )
        self.db.add(contract)
        self.db.flush()
        logger.info(
            "Created PerformanceContract %s for employee %s in cycle %s",
            contract.contract_id,
            employee_id,
            cycle_id,
        )
        return contract

    def sign_employee(
        self, org_id: UUID, contract_id: UUID
    ) -> PerformanceContract:
        """Record the employee's signature.

        If the supervisor has already signed, transitions the contract to ACTIVE.
        Otherwise sets status to PENDING_SIGNATURE.
        """
        contract = self.get_contract(org_id, contract_id)
        contract.employee_signed_date = date.today()

        if contract.supervisor_signed_date is not None:
            contract.status = ContractStatus.ACTIVE
            logger.info(
                "Contract %s activated — both parties have signed", contract_id
            )
        else:
            contract.status = ContractStatus.PENDING_SIGNATURE
            logger.info(
                "Contract %s pending supervisor signature", contract_id
            )

        self.db.flush()
        return contract

    def sign_supervisor(
        self, org_id: UUID, contract_id: UUID
    ) -> PerformanceContract:
        """Record the supervisor's signature.

        If the employee has already signed, transitions the contract to ACTIVE.
        Otherwise sets status to PENDING_SIGNATURE.
        """
        contract = self.get_contract(org_id, contract_id)
        contract.supervisor_signed_date = date.today()

        if contract.employee_signed_date is not None:
            contract.status = ContractStatus.ACTIVE
            logger.info(
                "Contract %s activated — both parties have signed", contract_id
            )
        else:
            contract.status = ContractStatus.PENDING_SIGNATURE
            logger.info(
                "Contract %s pending employee signature", contract_id
            )

        self.db.flush()
        return contract

    def countersign(
        self,
        org_id: UUID,
        contract_id: UUID,
        countersigner_id: UUID,
    ) -> PerformanceContract:
        """Record the HoD counter-signature and activate the contract.

        Counter-signing makes the contract valid regardless of employee
        signature status.
        """
        contract = self.get_contract(org_id, contract_id)
        contract.countersigner_id = countersigner_id
        contract.countersigner_date = date.today()
        contract.status = ContractStatus.ACTIVE

        self.db.flush()
        logger.info(
            "Contract %s countersigned and activated by %s",
            contract_id,
            countersigner_id,
        )
        return contract

    def check_30_day_requirement(self, org_id: UUID) -> list[dict]:
        """Find employees without active contracts within 30 days of joining/transfer/promotion."""
        from datetime import timedelta

        from app.models.people.hr.employee import Employee

        cutoff = date.today() - timedelta(days=30)

        # Employees who joined in the last 30 days
        stmt = select(Employee).where(
            Employee.organization_id == org_id,
            Employee.status == "ACTIVE",
            Employee.date_of_joining >= cutoff,
        )
        recent_employees = list(self.db.scalars(stmt).all())

        missing = []
        for emp in recent_employees:
            has_contract = self.db.scalar(
                select(PerformanceContract.contract_id).where(
                    PerformanceContract.organization_id == org_id,
                    PerformanceContract.employee_id == emp.employee_id,
                    PerformanceContract.status.in_(
                        [
                            ContractStatus.ACTIVE,
                            ContractStatus.PENDING_SIGNATURE,
                        ]
                    ),
                )
            )
            if not has_contract:
                missing.append(
                    {
                        "employee_id": emp.employee_id,
                        "employee_code": emp.employee_code,
                        "date_of_joining": emp.date_of_joining,
                        "days_since_joining": (date.today() - emp.date_of_joining).days,
                    }
                )

        return missing

    def amend_contract(
        self,
        org_id: UUID,
        contract_id: UUID,
        *,
        new_objectives: list[dict],
        amendment_reason: str,
        competency_ids: list | None = None,
    ) -> PerformanceContract:
        """Amend an existing contract by creating a replacement contract.

        The original contract status is set to AMENDED.  The new contract
        code has "-A" appended to the original code, and its
        ``amended_from_id`` points to the original.

        Raises:
            ContractValidationError: if new_objectives fail validation.
            ContractNotFoundError: if the original contract is not found.
        """
        self._validate_objectives(new_objectives)
        if competency_ids is not None and isinstance(competency_ids, list) and (
            competency_ids and isinstance(competency_ids[0], dict)
        ):
            self._validate_competency_selections(competency_ids)

        original = self.get_contract(org_id, contract_id)

        new_contract = PerformanceContract(
            organization_id=org_id,
            cycle_id=original.cycle_id,
            employee_id=original.employee_id,
            supervisor_id=original.supervisor_id,
            contract_code=f"{original.contract_code}-A",
            contract_type=original.contract_type,
            objectives=new_objectives,
            competency_ids=competency_ids,
            development_plan=original.development_plan,
            status=ContractStatus.DRAFT,
            amended_from_id=original.contract_id,
            amendment_reason=amendment_reason,
        )

        original.status = ContractStatus.AMENDED

        self.db.add(new_contract)
        self.db.flush()
        logger.info(
            "Contract %s amended → new contract %s (%s)",
            contract_id,
            new_contract.contract_id,
            new_contract.contract_code,
        )
        return new_contract

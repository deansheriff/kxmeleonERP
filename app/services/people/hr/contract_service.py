"""
Employment Contract Service — Core business logic for employee contracts.

Handles:
- Contract creation with auto-generated contract numbers
- Contract activation, renewal, and termination
- Expiring contract detection
- Paginated listing with filters
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.people.hr.employment_contract import (
    ContractStatus,
    ContractType,
    EmploymentContract,
)

logger = logging.getLogger(__name__)

# Valid status transitions
VALID_TRANSITIONS: dict[ContractStatus, list[ContractStatus]] = {
    ContractStatus.DRAFT: [ContractStatus.ACTIVE],
    ContractStatus.ACTIVE: [
        ContractStatus.TERMINATED,
        ContractStatus.EXPIRED,
        ContractStatus.RENEWED,
    ],
    ContractStatus.EXPIRING: [
        ContractStatus.TERMINATED,
        ContractStatus.EXPIRED,
        ContractStatus.RENEWED,
    ],
    ContractStatus.EXPIRED: [],
    ContractStatus.RENEWED: [],
    ContractStatus.TERMINATED: [],
}


class ContractService:
    """Service for managing employee employment contracts."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # =========================================================================
    # Read operations
    # =========================================================================

    def get_contract(
        self,
        organization_id: UUID,
        contract_id: UUID,
    ) -> EmploymentContract | None:
        """Get a single contract by ID, scoped to organization."""
        contract = self.db.get(EmploymentContract, contract_id)
        if contract and contract.organization_id != organization_id:
            return None
        return contract

    def _get_or_raise(
        self,
        organization_id: UUID,
        contract_id: UUID,
    ) -> EmploymentContract:
        """Get contract or raise ValueError."""
        contract = self.get_contract(organization_id, contract_id)
        if not contract:
            raise ValueError(f"Contract {contract_id} not found")
        return contract

    def list_contracts(
        self,
        organization_id: UUID,
        *,
        employee_id: UUID | None = None,
        status: ContractStatus | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[list[EmploymentContract], int]:
        """List contracts with filters and pagination."""
        stmt = select(EmploymentContract).where(
            EmploymentContract.organization_id == organization_id,
        )

        if employee_id is not None:
            stmt = stmt.where(EmploymentContract.employee_id == employee_id)
        if status is not None:
            stmt = stmt.where(EmploymentContract.status == status)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = self.db.scalar(count_stmt) or 0

        # Paginate
        stmt = stmt.order_by(EmploymentContract.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)
        contracts = list(self.db.scalars(stmt).all())

        return contracts, total

    def get_expiring_contracts(
        self,
        organization_id: UUID,
        days_ahead: int = 30,
    ) -> list[EmploymentContract]:
        """Get contracts expiring within N days from today."""
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)

        stmt = (
            select(EmploymentContract)
            .where(
                EmploymentContract.organization_id == organization_id,
                EmploymentContract.status.in_(
                    [ContractStatus.ACTIVE, ContractStatus.EXPIRING]
                ),
                EmploymentContract.end_date.isnot(None),
                EmploymentContract.end_date <= cutoff,
                EmploymentContract.end_date >= today,
            )
            .order_by(EmploymentContract.end_date.asc())
        )
        return list(self.db.scalars(stmt).all())

    # =========================================================================
    # Write operations
    # =========================================================================

    def _generate_contract_number(self, organization_id: UUID) -> str:
        """Generate next contract number: CT-YYYY-NNNN."""
        year = date.today().year

        count_stmt = select(func.count()).where(
            EmploymentContract.organization_id == organization_id,
            EmploymentContract.contract_number.like(f"CT-{year}-%"),
        )
        count = self.db.scalar(count_stmt) or 0
        next_seq = count + 1

        return f"CT-{year}-{next_seq:04d}"

    def create_contract(
        self,
        organization_id: UUID,
        employee_id: UUID,
        contract_type: ContractType,
        start_date: date,
        *,
        end_date: date | None = None,
        probation_end_date: date | None = None,
        terms: str | None = None,
        salary_amount: float | None = None,
        currency_code: str = "NGN",
        notice_period_days: int = 30,
        working_hours_per_week: float | None = None,
        notes: str | None = None,
        created_by_id: UUID | None = None,
    ) -> EmploymentContract:
        """Create a new employment contract in DRAFT status."""
        from decimal import Decimal

        contract_number = self._generate_contract_number(organization_id)

        contract = EmploymentContract(
            organization_id=organization_id,
            employee_id=employee_id,
            contract_number=contract_number,
            contract_type=contract_type,
            start_date=start_date,
            end_date=end_date,
            probation_end_date=probation_end_date,
            terms=terms,
            salary_amount=Decimal(str(salary_amount))
            if salary_amount is not None
            else None,
            currency_code=currency_code,
            notice_period_days=notice_period_days,
            working_hours_per_week=(
                Decimal(str(working_hours_per_week))
                if working_hours_per_week is not None
                else None
            ),
            notes=notes,
            status=ContractStatus.DRAFT,
            created_by_id=created_by_id,
        )
        self.db.add(contract)
        self.db.flush()

        logger.info(
            "Created contract %s for employee %s",
            contract.contract_number,
            employee_id,
        )
        return contract

    def activate_contract(
        self,
        organization_id: UUID,
        contract_id: UUID,
    ) -> EmploymentContract:
        """Transition contract from DRAFT to ACTIVE."""
        contract = self._get_or_raise(organization_id, contract_id)
        self._validate_transition(contract.status, ContractStatus.ACTIVE)

        contract.status = ContractStatus.ACTIVE
        self.db.flush()

        logger.info("Activated contract %s", contract.contract_number)
        return contract

    def renew_contract(
        self,
        organization_id: UUID,
        contract_id: UUID,
        new_end_date: date,
        *,
        new_start_date: date | None = None,
        created_by_id: UUID | None = None,
    ) -> EmploymentContract:
        """Renew a contract: mark old as RENEWED, create new DRAFT linked via previous_contract_id."""
        old = self._get_or_raise(organization_id, contract_id)
        self._validate_transition(old.status, ContractStatus.RENEWED)

        if old.end_date and new_end_date <= old.end_date:
            raise ValueError("New end date must be after the current contract end date")

        # Determine start date of new contract
        start = new_start_date or (
            old.end_date + timedelta(days=1) if old.end_date else date.today()
        )

        # Create new contract copying key terms
        new_contract = EmploymentContract(
            organization_id=organization_id,
            employee_id=old.employee_id,
            contract_number=self._generate_contract_number(organization_id),
            contract_type=old.contract_type,
            start_date=start,
            end_date=new_end_date,
            terms=old.terms,
            salary_amount=old.salary_amount,
            currency_code=old.currency_code,
            notice_period_days=old.notice_period_days,
            working_hours_per_week=old.working_hours_per_week,
            previous_contract_id=old.contract_id,
            status=ContractStatus.DRAFT,
            created_by_id=created_by_id,
        )
        self.db.add(new_contract)
        self.db.flush()

        # Mark old contract as renewed, link to new
        old.status = ContractStatus.RENEWED
        old.renewed_by_id = new_contract.contract_id
        self.db.flush()

        logger.info(
            "Renewed contract %s -> %s",
            old.contract_number,
            new_contract.contract_number,
        )
        return new_contract

    def terminate_contract(
        self,
        organization_id: UUID,
        contract_id: UUID,
    ) -> EmploymentContract:
        """Terminate an active/expiring contract."""
        contract = self._get_or_raise(organization_id, contract_id)
        self._validate_transition(contract.status, ContractStatus.TERMINATED)

        contract.status = ContractStatus.TERMINATED
        self.db.flush()

        logger.info("Terminated contract %s", contract.contract_number)
        return contract

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _validate_transition(
        current: ContractStatus,
        target: ContractStatus,
    ) -> None:
        """Validate a status transition, raise ValueError if invalid."""
        allowed = VALID_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise ValueError(
                f"Cannot transition contract from {current.value} to {target.value}"
            )

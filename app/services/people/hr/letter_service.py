"""
HR Letter Context Builder Service.

Builds context dicts for each HR letter type from employee data,
and provides a generic generate_letter() method that renders HTML/PDF
via DocumentGeneratorService.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.finance.automation.document_template import TemplateType
from app.models.finance.automation.generated_document import GeneratedDocument
from app.models.finance.core_org.organization import Organization
from app.models.people.hr.employee import Employee
from app.schemas.document_context import (
    ConfirmationLetterContext,
    SalaryRevisionLetterContext,
    TerminationLetterContext,
)
from app.schemas.hr_letter_context import (
    ExperienceLetterContext,
    PromotionLetterContext,
    RelievingLetterContext,
    TransferLetterContext,
)
from app.services.automation.document_generator import (
    DocumentGeneratorService,
)

logger = logging.getLogger(__name__)


class HRLetterServiceError(Exception):
    """Base error for HR letter service."""


class EmployeeNotFoundError(HRLetterServiceError):
    """Employee not found."""


# ---------------------------------------------------------------------------
# Mapping from TemplateType → context builder method name
# ---------------------------------------------------------------------------
_BUILDER_MAP: dict[TemplateType, str] = {
    TemplateType.CONFIRMATION_LETTER: "build_confirmation_context",
    TemplateType.PROMOTION_LETTER: "build_promotion_context",
    TemplateType.TRANSFER_LETTER: "build_transfer_context",
    TemplateType.TERMINATION_LETTER: "build_termination_context",
    TemplateType.SALARY_REVISION_LETTER: "build_salary_revision_context",
    TemplateType.EXPERIENCE_LETTER: "build_experience_context",
    TemplateType.RELIEVING_LETTER: "build_relieving_context",
}


class HRLetterService:
    """
    Service for building HR letter contexts and generating letters.

    Each ``build_*_context`` method hydrates a Pydantic context schema
    from the Employee model and supplementary ``extra`` kwargs.
    The ``generate_letter`` method wires the context builder into
    ``DocumentGeneratorService`` for end-to-end HTML/PDF generation.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._doc_service = DocumentGeneratorService(db)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_employee(self, employee_id: UUID) -> Employee:
        """Load employee with person, department, designation eagerly."""
        from sqlalchemy import select

        stmt = (
            select(Employee)
            .options(
                joinedload(Employee.person),
                joinedload(Employee.department),
                joinedload(Employee.designation),
                joinedload(Employee.organization),
            )
            .where(Employee.employee_id == employee_id)
        )
        employee = self.db.scalar(stmt)
        if not employee:
            raise EmployeeNotFoundError(f"Employee {employee_id} not found")
        return employee

    def _get_org(self, org_id: UUID) -> Organization:
        org = self.db.get(Organization, org_id)
        if not org:
            raise HRLetterServiceError(f"Organization {org_id} not found")
        return org

    @staticmethod
    def _org_name(org: Organization) -> str:
        return org.trading_name or org.legal_name

    @staticmethod
    def _org_address(org: Organization) -> str:
        parts = [
            org.address_line1,
            org.address_line2,
            org.city,
            org.state,
            org.postal_code,
            org.country,
        ]
        return ", ".join(p for p in parts if p)

    @staticmethod
    def _employee_name(emp: Employee) -> str:
        first = emp.first_name or ""
        last = emp.last_name or ""
        name = f"{first} {last}".strip()
        return name or emp.employee_code

    @staticmethod
    def _job_title(emp: Employee) -> str:
        if emp.designation:
            return emp.designation.designation_name
        return "Employee"

    @staticmethod
    def _department_name(emp: Employee) -> str | None:
        if emp.department:
            return emp.department.department_name
        return None

    # ------------------------------------------------------------------
    # Context builders
    # ------------------------------------------------------------------

    def build_confirmation_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        new_salary: Decimal | None = None,
        salary_effective_date: date | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a post-probation confirmation letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        confirmation_date = emp.confirmation_date or date.today()
        probation_end = emp.probation_end_date or confirmation_date

        ctx = ConfirmationLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            job_title=self._job_title(emp),
            department_name=self._department_name(emp),
            start_date=emp.date_of_joining,
            probation_end_date=probation_end,
            confirmation_date=confirmation_date,
            current_salary=emp.ctc or Decimal("0"),
            new_salary=new_salary,
            salary_effective_date=salary_effective_date,
            organization_name=self._org_name(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_promotion_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        new_job_title: str,
        new_salary: Decimal,
        effective_date: date,
        new_department: str | None = None,
        promotion_reason: str | None = None,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a promotion letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        previous_salary = emp.ctc or Decimal("0")
        increment = new_salary - previous_salary
        pct = (increment / previous_salary * 100) if previous_salary else Decimal("0")

        ctx = PromotionLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            previous_job_title=self._job_title(emp),
            previous_department=self._department_name(emp),
            previous_salary=previous_salary,
            new_job_title=new_job_title,
            new_department=new_department or self._department_name(emp),
            new_salary=new_salary,
            salary_increment=increment,
            salary_increment_percentage=pct.quantize(Decimal("0.01")),
            effective_date=effective_date,
            promotion_reason=promotion_reason,
            organization_name=self._org_name(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            letter_date=date.today(),
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_transfer_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        new_job_title: str,
        effective_date: date,
        new_department: str | None = None,
        new_location: str | None = None,
        new_reporting_to: str | None = None,
        transfer_reason: str | None = None,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a transfer letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        current_location: str | None = None
        if emp.assigned_location:
            current_location = getattr(emp.assigned_location, "location_name", None)

        ctx = TransferLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            current_department=self._department_name(emp),
            current_location=current_location,
            current_job_title=self._job_title(emp),
            new_department=new_department,
            new_location=new_location,
            new_job_title=new_job_title,
            new_reporting_to=new_reporting_to,
            effective_date=effective_date,
            transfer_reason=transfer_reason,
            organization_name=self._org_name(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            letter_date=date.today(),
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_termination_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        termination_date: date,
        last_working_date: date,
        termination_reason: str,
        termination_type: str = "INVOLUNTARY",
        notice_period_served: bool = True,
        notice_period_days: int = 30,
        total_settlement: Decimal = Decimal("0"),
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a termination letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        ctx = TerminationLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            job_title=self._job_title(emp),
            department_name=self._department_name(emp),
            termination_date=termination_date,
            last_working_date=last_working_date,
            letter_date=date.today(),
            termination_reason=termination_reason,
            termination_type=termination_type,
            notice_period_served=notice_period_served,
            notice_period_days=notice_period_days,
            total_settlement=total_settlement,
            accrued_leave_days=0,
            organization_name=self._org_name(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_salary_revision_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        new_salary: Decimal,
        effective_date: date,
        revision_reason: str = "Annual Review",
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a salary revision letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        current_salary = emp.ctc or Decimal("0")
        increment = new_salary - current_salary
        pct = (increment / current_salary * 100) if current_salary else Decimal("0")

        ctx = SalaryRevisionLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            job_title=self._job_title(emp),
            department_name=self._department_name(emp),
            current_salary=current_salary,
            new_salary=new_salary,
            increment_amount=increment,
            increment_percentage=pct.quantize(Decimal("0.01")),
            effective_date=effective_date,
            revision_reason=revision_reason,
            organization_name=self._org_name(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            letter_date=date.today(),
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_experience_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        date_of_leaving: date | None = None,
        role_summary: str | None = None,
        achievements: list[str] | None = None,
        conduct_rating: str | None = None,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for an experience / service certificate letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        leaving = date_of_leaving or emp.date_of_leaving or date.today()

        ctx = ExperienceLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            date_of_joining=emp.date_of_joining,
            date_of_leaving=leaving,
            job_title=self._job_title(emp),
            designation_name=self._job_title(emp),
            department_name=self._department_name(emp),
            role_summary=role_summary,
            achievements=achievements,
            conduct_rating=conduct_rating,
            organization_name=self._org_name(org),
            organization_legal_name=org.legal_name,
            organization_address=self._org_address(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            letter_date=date.today(),
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    def build_relieving_context(
        self,
        org_id: UUID,
        employee_id: UUID,
        *,
        last_working_day: date | None = None,
        clearance_completed: bool = False,
        final_settlement_completed: bool = False,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build context for a relieving letter."""
        emp = self._get_employee(employee_id)
        org = self._get_org(org_id)

        lwd = last_working_day or emp.date_of_leaving or date.today()

        ctx = RelievingLetterContext(
            employee_name=self._employee_name(emp),
            employee_code=emp.employee_code,
            job_title=self._job_title(emp),
            department_name=self._department_name(emp),
            date_of_joining=emp.date_of_joining,
            last_working_day=lwd,
            clearance_completed=clearance_completed,
            final_settlement_completed=final_settlement_completed,
            organization_name=self._org_name(org),
            organization_legal_name=org.legal_name,
            organization_address=self._org_address(org),
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            letter_date=date.today(),
        )
        result = ctx.model_dump()
        if extra:
            result.update(extra)
        return result

    # ------------------------------------------------------------------
    # Generic generate_letter
    # ------------------------------------------------------------------

    def generate_letter(
        self,
        org_id: UUID,
        employee_id: UUID,
        template_type: TemplateType,
        user_id: UUID,
        *,
        extra_context: dict[str, Any] | None = None,
        template_name: str | None = None,
        signatory_name: str = "Human Resources",
        signatory_title: str = "HR Department",
    ) -> tuple[bytes, GeneratedDocument | None]:
        """
        End-to-end letter generation.

        1. Looks up the default template for *template_type*.
        2. Builds the context via the appropriate ``build_*_context`` method.
        3. Renders HTML/PDF through ``DocumentGeneratorService``.

        Returns:
            ``(pdf_bytes, GeneratedDocument | None)``
        """
        builder_name = _BUILDER_MAP.get(template_type)
        if not builder_name:
            raise HRLetterServiceError(
                f"No context builder registered for {template_type.value}"
            )

        builder = getattr(self, builder_name)

        # Merge signatory into extra_context so builders can use them
        merged_extra = dict(extra_context) if extra_context else {}
        ctx = builder(
            org_id,
            employee_id,
            signatory_name=signatory_name,
            signatory_title=signatory_title,
            extra=merged_extra if merged_extra else None,
        )

        # Ensure default templates exist
        self._ensure_default_templates(org_id, user_id, template_type)

        emp = self._get_employee(employee_id)

        pdf_bytes, doc_record = self._doc_service.generate_pdf(
            organization_id=org_id,
            template_type=template_type,
            context=ctx,
            template_name=template_name,
            entity_type="EMPLOYEE",
            entity_id=emp.employee_id,
            document_number=f"{template_type.value}-{emp.employee_code}",
            document_title=f"{template_type.value.replace('_', ' ').title()} - {self._employee_name(emp)}",
            created_by=user_id,
            save_record=True,
            use_base_template=True,
        )

        logger.info(
            "Generated %s for employee %s (%s)",
            template_type.value,
            emp.employee_code,
            self._employee_name(emp),
        )

        return pdf_bytes, doc_record

    def _ensure_default_templates(
        self,
        org_id: UUID,
        user_id: UUID,
        template_type: TemplateType,
    ) -> None:
        """Seed a default template if none exists for the given type."""
        existing = self._doc_service.get_template(org_id, template_type, None)
        if existing:
            return

        from app.services.people.hr.default_letter_templates import (
            DEFAULT_LETTER_TEMPLATES,
            _template_display_name,
        )

        content = DEFAULT_LETTER_TEMPLATES.get(template_type)
        if not content:
            logger.warning("No default template content for %s", template_type.value)
            return

        from app.models.finance.automation.document_template import DocumentTemplate

        template = DocumentTemplate(
            organization_id=org_id,
            template_type=template_type,
            template_name=_template_display_name(template_type),
            description=f"System default {template_type.value.replace('_', ' ').lower()} template",
            template_content=content,
            page_size="A4",
            page_orientation="portrait",
            is_default=True,
            is_active=True,
            version=1,
            created_by=user_id,
        )
        self.db.add(template)
        self.db.flush()
        logger.info(
            "Seeded default template for %s (org %s)", template_type.value, org_id
        )

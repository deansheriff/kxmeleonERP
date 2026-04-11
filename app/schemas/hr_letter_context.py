"""
HR Letter Context Schemas.

Pydantic models defining the expected context variables for HR letter types
that are not yet covered in document_context.py.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.config import settings


class AppointmentLetterContext(BaseModel):
    """Context for APPOINTMENT_LETTER template (formal appointment after offer acceptance)."""

    model_config = ConfigDict(from_attributes=True)

    # Employee information
    employee_name: str
    employee_code: str
    employee_address: str | None = None

    # Position details
    job_title: str
    designation_name: str
    department_name: str | None = None
    reporting_to: str | None = None
    location: str | None = None
    employment_type: str = "FULL_TIME"

    # Compensation
    base_salary: Decimal
    currency_code: str = settings.default_functional_currency_code
    pay_frequency: str = "MONTHLY"

    # Allowances
    allowances: list[dict[str, Decimal | str]] | None = None

    # Dates
    appointment_date: date
    start_date: date
    letter_date: date

    # Terms
    probation_months: int = 3
    notice_period_days: int = 30
    work_hours_per_week: int = 40
    work_days: str | None = None

    # Organization
    organization_name: str
    organization_legal_name: str | None = None
    organization_address: str | None = None
    organization_logo_url: str | None = None

    # Signatory
    signatory_name: str
    signatory_title: str


class PromotionLetterContext(BaseModel):
    """Context for PROMOTION_LETTER template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str
    employee_address: str | None = None

    # Previous position
    previous_job_title: str
    previous_department: str | None = None
    previous_salary: Decimal

    # New position
    new_job_title: str
    new_department: str | None = None
    new_salary: Decimal
    currency_code: str = settings.default_functional_currency_code

    # Change details
    salary_increment: Decimal
    salary_increment_percentage: Decimal
    effective_date: date

    # Reason
    promotion_reason: str | None = None

    # Organization
    organization_name: str

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date


class TransferLetterContext(BaseModel):
    """Context for TRANSFER_LETTER template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str
    employee_address: str | None = None

    # Current assignment
    current_department: str | None = None
    current_location: str | None = None
    current_job_title: str

    # New assignment
    new_department: str | None = None
    new_location: str | None = None
    new_job_title: str
    new_reporting_to: str | None = None

    # Transfer details
    effective_date: date
    transfer_reason: str | None = None

    # Organization
    organization_name: str

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date


class ResignationAcceptanceContext(BaseModel):
    """Context for RESIGNATION_ACCEPTANCE template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str
    employee_address: str | None = None

    # Position
    job_title: str
    department_name: str | None = None

    # Resignation details
    resignation_date: date
    last_working_day: date
    notice_period_days: int

    # Settlement
    accrued_leave_days: int | None = None
    leave_encashment_amount: Decimal | None = None
    currency_code: str = settings.default_functional_currency_code

    # Exit requirements
    handover_instructions: str | None = None
    exit_interview_date: date | None = None

    # Organization
    organization_name: str

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date


class ExperienceLetterContext(BaseModel):
    """Context for EXPERIENCE_LETTER template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str

    # Employment period
    date_of_joining: date
    date_of_leaving: date

    # Position history
    job_title: str
    designation_name: str | None = None
    department_name: str | None = None

    # Role summary
    role_summary: str | None = None
    achievements: list[str] | None = None

    # Conduct
    conduct_rating: str | None = None  # e.g., "Excellent", "Good"

    # Organization
    organization_name: str
    organization_legal_name: str | None = None
    organization_address: str | None = None

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date


class RelievingLetterContext(BaseModel):
    """Context for RELIEVING_LETTER template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str

    # Position
    job_title: str
    department_name: str | None = None

    # Dates
    date_of_joining: date
    last_working_day: date

    # Clearance
    clearance_completed: bool = False
    final_settlement_completed: bool = False

    # Organization
    organization_name: str
    organization_legal_name: str | None = None
    organization_address: str | None = None

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date


class BonusLetterContext(BaseModel):
    """Context for BONUS_LETTER template."""

    model_config = ConfigDict(from_attributes=True)

    # Employee
    employee_name: str
    employee_code: str

    # Position
    job_title: str
    department_name: str | None = None

    # Bonus details
    bonus_amount: Decimal
    currency_code: str = settings.default_functional_currency_code
    bonus_reason: str  # e.g., "Annual Performance Bonus", "Festival Bonus"
    bonus_period: str | None = None  # e.g., "FY 2025-26", "Q4 2025"
    payment_date: date | None = None

    # Organization
    organization_name: str

    # Signatory
    signatory_name: str
    signatory_title: str

    # Reference
    letter_date: date

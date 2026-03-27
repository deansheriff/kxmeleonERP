from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.people.payroll.data_completeness import (
    PayrollIssueType,
    PayrollReadinessService,
)


def _employee(*, employment_type=None, salary_mode=None, date_of_joining_value=None):
    return SimpleNamespace(
        employee_id=uuid4(),
        employee_code="EMP-001",
        full_name="Contract Worker",
        department=SimpleNamespace(department_name="Operations"),
        employment_type=employment_type,
        employment_type_id=None,
        salary_mode=salary_mode,
        bank_account_number=None,
        bank_name=None,
        date_of_joining=date_of_joining_value or date(2025, 12, 1),
        date_of_leaving=None,
    )


def _assignment(structure_name: str):
    return SimpleNamespace(
        assignment_id=uuid4(),
        structure_id=uuid4(),
        salary_structure=SimpleNamespace(structure_name=structure_name),
    )


def test_contract_staff_without_tax_profile_is_not_flagged_for_review():
    db = MagicMock()
    service = PayrollReadinessService(db)
    employee = _employee(
        employment_type=SimpleNamespace(type_code="CONTRACT", type_name="Contract")
    )
    readiness = service._check_employee_readiness(
        employee=employee,
        assignment=_assignment("Contract Staff"),
        tax_profile=None,
        attendance=None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )

    assert readiness.is_contract_staff is True
    assert readiness.needs_review is False
    assert PayrollIssueType.MISSING_TAX_PROFILE not in {
        issue.issue_type for issue in readiness.issues
    }
    assert "No tax profile - PAYE may not calculate accurately" not in (
        readiness.review_reasons
    )


def test_regular_staff_without_tax_profile_is_flagged_for_review():
    db = MagicMock()
    service = PayrollReadinessService(db)
    employee = _employee(
        employment_type=SimpleNamespace(type_code="FULL_TIME", type_name="Full Time")
    )
    readiness = service._check_employee_readiness(
        employee=employee,
        assignment=_assignment("General Staff"),
        tax_profile=None,
        attendance=None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )

    assert readiness.is_contract_staff is False
    assert readiness.needs_review is True
    assert PayrollIssueType.MISSING_TAX_PROFILE in {
        issue.issue_type for issue in readiness.issues
    }

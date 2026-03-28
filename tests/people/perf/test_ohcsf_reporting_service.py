"""
Tests for OHCSFReportingService.

Light structural tests — the query-heavy internals are best covered
by integration tests against a real database. These tests verify:
- The service can be imported and instantiated
- Every public method exists with the correct signature
- Return types are as documented
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.people.perf.ohcsf_reporting_service import OHCSFReportingService


ORG_ID = uuid4()
CYCLE_ID = uuid4()


@pytest.fixture
def svc() -> OHCSFReportingService:
    """Service with a mock DB session — we test structure, not queries."""
    db = MagicMock()
    # scalars().all() → empty list by default
    db.scalars.return_value.all.return_value = []
    # scalar() → None / 0 by default
    db.scalar.return_value = 0
    # execute().all() → empty list by default
    db.execute.return_value.all.return_value = []
    db.execute.return_value.mappings.return_value.all.return_value = []
    return OHCSFReportingService(db)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


def test_service_instantiation(svc: OHCSFReportingService) -> None:
    assert isinstance(svc, OHCSFReportingService)


# ---------------------------------------------------------------------------
# Report 1 — rating_summary
# ---------------------------------------------------------------------------


def test_rating_summary_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.rating_summary(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "ratings" in result
    assert "total" in result
    assert isinstance(result["ratings"], list)


def test_rating_summary_structure(svc: OHCSFReportingService) -> None:
    result = svc.rating_summary(ORG_ID, CYCLE_ID)
    # Empty DB → zero total, populated label rows
    assert result["total"] == 0
    for row in result["ratings"]:
        assert "label" in row
        assert "count" in row
        assert "percentage" in row


# ---------------------------------------------------------------------------
# Report 2 — rating_by_department
# ---------------------------------------------------------------------------


def test_rating_by_department_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.rating_by_department(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "departments" in result
    assert "total" in result


# ---------------------------------------------------------------------------
# Report 3 — rating_by_grade_level
# ---------------------------------------------------------------------------


def test_rating_by_grade_level_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.rating_by_grade_level(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "grades" in result
    assert "total" in result


# ---------------------------------------------------------------------------
# Report 4 — distribution_org_wide
# ---------------------------------------------------------------------------


def test_distribution_org_wide_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.distribution_org_wide(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "distribution" in result
    assert "total" in result


# ---------------------------------------------------------------------------
# Report 5 — distribution_by_department
# ---------------------------------------------------------------------------


def test_distribution_by_department_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.distribution_by_department(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "departments" in result
    assert "total" in result


# ---------------------------------------------------------------------------
# Report 6 — distribution_by_grade
# ---------------------------------------------------------------------------


def test_distribution_by_grade_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.distribution_by_grade(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "grades" in result
    assert "total" in result


# ---------------------------------------------------------------------------
# Report 7 — top_performers
# ---------------------------------------------------------------------------


def test_top_performers_returns_list(svc: OHCSFReportingService) -> None:
    result = svc.top_performers(ORG_ID, CYCLE_ID)
    assert isinstance(result, list)


def test_top_performers_accepts_n_kwarg(svc: OHCSFReportingService) -> None:
    result = svc.top_performers(ORG_ID, CYCLE_ID, n=5)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Report 8 — bottom_performers
# ---------------------------------------------------------------------------


def test_bottom_performers_returns_list(svc: OHCSFReportingService) -> None:
    result = svc.bottom_performers(ORG_ID, CYCLE_ID)
    assert isinstance(result, list)


def test_bottom_performers_accepts_n_kwarg(svc: OHCSFReportingService) -> None:
    result = svc.bottom_performers(ORG_ID, CYCLE_ID, n=5)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Report 9 — development_needs_overview
# ---------------------------------------------------------------------------


def test_development_needs_overview_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.development_needs_overview(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "total_with_needs" in result
    assert "total_appraisals" in result
    assert "needs_list" in result
    assert isinstance(result["needs_list"], list)


# ---------------------------------------------------------------------------
# Report 10 — development_needs_by_department
# ---------------------------------------------------------------------------


def test_development_needs_by_department_returns_dict(
    svc: OHCSFReportingService,
) -> None:
    result = svc.development_needs_by_department(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)
    assert "departments" in result
    assert "total" in result


def test_development_needs_by_department_accepts_department_id(
    svc: OHCSFReportingService,
) -> None:
    dept_id = uuid4()
    result = svc.development_needs_by_department(ORG_ID, CYCLE_ID, department_id=dept_id)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Report 11 — cycle_compliance_dashboard
# ---------------------------------------------------------------------------


def test_compliance_dashboard_returns_dict(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    assert isinstance(result, dict)


def test_compliance_dashboard_structure(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    required_keys = {
        "contracts",
        "monthly_reviews",
        "appraisals",
        "appeals",
        "pips",
    }
    assert required_keys.issubset(result.keys())


def test_compliance_dashboard_contracts_section(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    contracts = result["contracts"]
    assert "total" in contracts
    assert "signed" in contracts
    assert "unsigned" in contracts
    assert "compliance_pct" in contracts


def test_compliance_dashboard_appraisals_section(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    appraisals = result["appraisals"]
    assert "total" in appraisals
    assert "completed" in appraisals
    assert "pending" in appraisals
    assert "completion_pct" in appraisals


def test_compliance_dashboard_appeals_section(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    appeals = result["appeals"]
    assert "total" in appeals
    assert "pending" in appeals
    assert "resolved" in appeals


def test_compliance_dashboard_pips_section(svc: OHCSFReportingService) -> None:
    result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
    pips = result["pips"]
    assert "active" in pips

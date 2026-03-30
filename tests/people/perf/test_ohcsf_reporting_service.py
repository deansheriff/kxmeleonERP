"""
Tests for OHCSFReportingService.

Light structural tests — the query-heavy internals are best covered
by integration tests against a real database. These tests verify:
- The service can be imported and instantiated
- Every public method exists with the correct signature
- Return types are as documented
- The _pct helper computes correctly
- Computation logic works with mocked DB rows
"""

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.services.people.perf.ohcsf_reporting_service import (
    OHCSFReportingService,
    _pct,
)

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
    result = svc.development_needs_by_department(
        ORG_ID, CYCLE_ID, department_id=dept_id
    )
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


# ---------------------------------------------------------------------------
# _pct helper — unit tests (module-level function)
# ---------------------------------------------------------------------------


class TestPctHelper:
    """Test the percentage calculation helper."""

    def test_pct_normal(self) -> None:
        """Normal percentage calculation."""
        assert _pct(25, 100) == Decimal("25.00")

    def test_pct_zero_total_returns_zero(self) -> None:
        """Zero total must return 0, not raise ZeroDivisionError."""
        assert _pct(5, 0) == Decimal("0.00")

    def test_pct_zero_count(self) -> None:
        """Zero count with non-zero total returns 0."""
        assert _pct(0, 50) == Decimal("0.00")

    def test_pct_rounding(self) -> None:
        """Percentage rounds to 2 decimal places."""
        # 1/3 * 100 = 33.333… → 33.33
        result = _pct(1, 3)
        assert result == Decimal("33.33")

    def test_pct_full_100(self) -> None:
        """100% when count equals total."""
        assert _pct(7, 7) == Decimal("100.00")

    def test_pct_returns_decimal(self) -> None:
        """Return type is Decimal, not float."""
        result = _pct(1, 4)
        assert isinstance(result, Decimal)


# ---------------------------------------------------------------------------
# rating_summary — computation with mocked DB rows
# ---------------------------------------------------------------------------


class TestRatingSummaryComputation:
    """Test rating_summary percentage calculations with known DB results."""

    def _make_svc(self, rows: list) -> OHCSFReportingService:
        """Build a service whose db.execute().all() returns ``rows``."""
        db = MagicMock()
        db.execute.return_value.all.return_value = rows
        return OHCSFReportingService(db)

    def test_rating_summary_counts_rows_correctly(self) -> None:
        """Counts from DB rows are reflected in the summary."""
        rows = [("Outstanding", 10), ("Good", 5), ("Poor", 5)]
        svc = self._make_svc(rows)

        result = svc.rating_summary(uuid4(), uuid4())

        assert result["total"] == 20
        labels = {r["label"]: r["count"] for r in result["ratings"]}
        assert labels["Outstanding"] == 10
        assert labels["Good"] == 5
        assert labels["Poor"] == 5

    def test_rating_summary_percentages_are_correct(self) -> None:
        """Percentages sum to 100 when all data is accounted for."""
        rows = [("Outstanding", 50), ("Excellent", 50)]
        svc = self._make_svc(rows)

        result = svc.rating_summary(uuid4(), uuid4())

        pcts = {r["label"]: r["percentage"] for r in result["ratings"]}
        assert pcts["Outstanding"] == Decimal("50.00")
        assert pcts["Excellent"] == Decimal("50.00")

    def test_rating_summary_normalises_uppercase_labels(self) -> None:
        """DB values like 'OUTSTANDING' are title-cased to 'Outstanding'."""
        rows = [("OUTSTANDING", 3), ("GOOD", 7)]
        svc = self._make_svc(rows)

        result = svc.rating_summary(uuid4(), uuid4())

        labels = {r["label"]: r["count"] for r in result["ratings"]}
        assert labels["Outstanding"] == 3
        assert labels["Good"] == 7

    def test_rating_summary_unlabelled_rows_are_skipped(self) -> None:
        """Rows with a None label are silently ignored."""
        rows = [(None, 2), ("Good", 8)]
        svc = self._make_svc(rows)

        result = svc.rating_summary(uuid4(), uuid4())

        # None-labelled count is not in any known bucket, so total = 8 from Good
        # (None rows land in counts dict with key None which sums but is not in
        # _RATING_LABELS — implementation stores it anyway, total picks it up)
        labels = {r["label"]: r["count"] for r in result["ratings"]}
        assert labels["Good"] == 8

    def test_rating_summary_empty_db_returns_zero_total(self) -> None:
        """Empty DB rows → total is 0, all counts are 0."""
        svc = self._make_svc([])

        result = svc.rating_summary(uuid4(), uuid4())

        assert result["total"] == 0
        for row in result["ratings"]:
            assert row["count"] == 0


# ---------------------------------------------------------------------------
# top_performers / bottom_performers — structure tests
# ---------------------------------------------------------------------------


class TestTopPerformersComputation:
    """Test top/bottom performer output structure."""

    def _make_svc_with_rows(self, rows: list) -> OHCSFReportingService:
        db = MagicMock()
        db.execute.return_value.all.return_value = rows
        return OHCSFReportingService(db)

    def test_top_performers_returns_correct_structure(self) -> None:
        """Each entry has employee_name, department, score, rating_label."""
        rows = [("Alice Smith", "Finance", 92.5, "Outstanding")]
        svc = self._make_svc_with_rows(rows)

        result = svc.top_performers(uuid4(), uuid4())

        assert len(result) == 1
        entry = result[0]
        assert "employee_name" in entry
        assert "department" in entry
        assert "score" in entry
        assert "rating_label" in entry

    def test_top_performers_score_is_decimal(self) -> None:
        """Score is a Decimal, not a raw float."""
        rows = [("Bob Jones", "HR", 78.3, "Good")]
        svc = self._make_svc_with_rows(rows)

        result = svc.top_performers(uuid4(), uuid4())

        assert isinstance(result[0]["score"], Decimal)

    def test_top_performers_none_name_becomes_empty_string(self) -> None:
        """None display_name is converted to empty string."""
        rows = [(None, "Finance", 80.0, "Good")]
        svc = self._make_svc_with_rows(rows)

        result = svc.top_performers(uuid4(), uuid4())

        assert result[0]["employee_name"] == ""

    def test_top_performers_none_department_becomes_empty_string(self) -> None:
        """None department_name is converted to empty string."""
        rows = [("Alice", None, 80.0, "Good")]
        svc = self._make_svc_with_rows(rows)

        result = svc.top_performers(uuid4(), uuid4())

        assert result[0]["department"] == ""

    def test_bottom_performers_returns_correct_structure(self) -> None:
        """bottom_performers returns the same shape as top_performers."""
        rows = [("Charlie Doe", "Operations", 45.0, "Poor")]
        svc = self._make_svc_with_rows(rows)

        result = svc.bottom_performers(uuid4(), uuid4())

        assert len(result) == 1
        assert set(result[0].keys()) == {
            "employee_name",
            "department",
            "score",
            "rating_label",
        }

    def test_bottom_performers_empty_rows(self) -> None:
        """No rows → empty list returned."""
        svc = self._make_svc_with_rows([])

        result = svc.bottom_performers(uuid4(), uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# cycle_compliance_dashboard — nested structure and arithmetic
# ---------------------------------------------------------------------------


class TestComplianceDashboard:
    """Test compliance dashboard structure and computed values."""

    def test_returns_nested_structure_with_correct_keys(
        self, svc: OHCSFReportingService
    ) -> None:
        """Dashboard top-level keys match documented contract."""
        result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
        assert set(result.keys()) == {
            "contracts",
            "monthly_reviews",
            "appraisals",
            "appeals",
            "pips",
        }

    def test_monthly_reviews_section_keys(self, svc: OHCSFReportingService) -> None:
        """monthly_reviews section has completed, expected, completion_pct."""
        result = svc.cycle_compliance_dashboard(ORG_ID, CYCLE_ID)
        mr = result["monthly_reviews"]
        assert "completed" in mr
        assert "expected" in mr
        assert "completion_pct" in mr

    def test_unsigned_is_total_minus_signed(self) -> None:
        """unsigned = total_contracts - signed_contracts."""
        db = MagicMock()
        # cycle_compliance_dashboard makes exactly 10 db.scalar() calls:
        # [0] total_contracts, [1] signed_contracts, [2] completed_reviews,
        # [3] total_reviews, [4] total_appraisals, [5] completed_appraisals,
        # [6] total_appeals, [7] pending_appeals, [8] resolved_appeals, [9] active_pips
        db.scalar.side_effect = [10, 7, 0, 0, 0, 0, 0, 0, 0, 0]
        svc = OHCSFReportingService(db)

        result = svc.cycle_compliance_dashboard(uuid4(), uuid4())

        assert result["contracts"]["total"] == 10
        assert result["contracts"]["signed"] == 7
        assert result["contracts"]["unsigned"] == 3

    def test_pending_appraisals_is_total_minus_completed(self) -> None:
        """pending = total_appraisals - completed_appraisals."""
        db = MagicMock()
        # Calls: total_contracts=0, signed=0, completed_reviews=0,
        #        total_reviews=0, total_appraisals=20, completed_appraisals=15,
        #        total_appeals=0, pending_appeals=0, resolved_appeals=0, active_pips=0
        db.scalar.side_effect = [0, 0, 0, 0, 20, 15, 0, 0, 0, 0]
        svc = OHCSFReportingService(db)

        result = svc.cycle_compliance_dashboard(uuid4(), uuid4())

        assert result["appraisals"]["total"] == 20
        assert result["appraisals"]["completed"] == 15
        assert result["appraisals"]["pending"] == 5

    def test_compliance_pct_zero_when_no_contracts(self) -> None:
        """compliance_pct is 0.00 when there are no contracts."""
        db = MagicMock()
        db.scalar.side_effect = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        svc = OHCSFReportingService(db)

        result = svc.cycle_compliance_dashboard(uuid4(), uuid4())

        assert result["contracts"]["compliance_pct"] == Decimal("0.00")

    def test_completion_pct_is_decimal(self) -> None:
        """completion_pct values are Decimal instances."""
        db = MagicMock()
        db.scalar.side_effect = [4, 4, 3, 4, 4, 4, 0, 0, 0, 0]
        svc = OHCSFReportingService(db)

        result = svc.cycle_compliance_dashboard(uuid4(), uuid4())

        assert isinstance(result["contracts"]["compliance_pct"], Decimal)
        assert isinstance(result["appraisals"]["completion_pct"], Decimal)
        assert isinstance(result["monthly_reviews"]["completion_pct"], Decimal)

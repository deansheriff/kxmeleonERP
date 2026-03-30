"""
Tests for InstitutionalPerformanceService — OHCSF PMS.

Tests focus on:
- Error class hierarchy
- create_for_cycle: criteria initialisation from templates
- score_criteria: raw/weighted scoring and composite computation
- reconcile_with_employee_ratings: pre-reconciliation snapshot and adjustment

Uses MagicMock for the DB session so no DB is required.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.people.perf.institutional_performance import (
    InstitutionalCriteriaTemplate,
    InstitutionalPerformance,
)
from app.models.people.perf.pms_enums import (
    InstitutionalPerfStatus,
    InstitutionType,
)
from app.services.people.perf.institutional_service import (
    InstitutionalPerfNotFoundError,
    InstitutionalPerformanceService,
    InstitutionalServiceError,
    InstitutionalValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_ID = uuid.uuid4()
CYCLE_ID = uuid.uuid4()
DEPT_ID = uuid.uuid4()
INST_PERF_ID = uuid.uuid4()
RECONCILER_ID = uuid.uuid4()


def make_service() -> InstitutionalPerformanceService:
    db = MagicMock()
    return InstitutionalPerformanceService(db)


def make_template(
    criteria_name: str,
    default_weight: int,
    sequence: int,
    institution_type: InstitutionType = InstitutionType.MINISTRY,
) -> InstitutionalCriteriaTemplate:
    tmpl = InstitutionalCriteriaTemplate(
        organization_id=ORG_ID,
        institution_type=institution_type,
        criteria_name=criteria_name,
        default_weight=default_weight,
        sequence=sequence,
        is_active=True,
    )
    tmpl.template_id = uuid.uuid4()
    return tmpl


def make_inst_perf(
    *,
    status: InstitutionalPerfStatus = InstitutionalPerfStatus.DRAFT,
    criteria_scores: list | None = None,
    composite_score: Decimal | None = None,
    rating_label: str | None = None,
) -> InstitutionalPerformance:
    ip = InstitutionalPerformance(
        organization_id=ORG_ID,
        cycle_id=CYCLE_ID,
        institution_type=InstitutionType.MINISTRY,
        status=status,
        criteria_scores=criteria_scores,
        composite_score=composite_score,
        rating_label=rating_label,
        is_reconciled=False,
    )
    ip.inst_perf_id = INST_PERF_ID
    return ip


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_not_found_is_base(self) -> None:
        err = InstitutionalPerfNotFoundError(uuid.uuid4())
        assert isinstance(err, InstitutionalServiceError)

    def test_validation_is_base(self) -> None:
        err = InstitutionalValidationError("bad input")
        assert isinstance(err, InstitutionalServiceError)

    def test_not_found_message_contains_id(self) -> None:
        some_id = uuid.uuid4()
        err = InstitutionalPerfNotFoundError(some_id)
        assert str(some_id) in str(err)

    def test_validation_message_preserved(self) -> None:
        err = InstitutionalValidationError("weight must be positive")
        assert "weight must be positive" in str(err)


# ---------------------------------------------------------------------------
# get_institutional_perf
# ---------------------------------------------------------------------------


class TestGetInstitutionalPerf:
    def test_returns_record_when_found(self) -> None:
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        result = svc.get_institutional_perf(ORG_ID, INST_PERF_ID)

        assert result is ip

    def test_raises_not_found_when_missing(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(InstitutionalPerfNotFoundError) as exc_info:
            svc.get_institutional_perf(ORG_ID, INST_PERF_ID)

        assert exc_info.value.inst_perf_id == INST_PERF_ID


# ---------------------------------------------------------------------------
# list_institutional_perfs
# ---------------------------------------------------------------------------


class TestListInstitutionalPerfs:
    def test_returns_paginated_result(self) -> None:
        svc = make_service()
        ip = make_inst_perf()

        # Mock the db.scalars().all() chain used by paginate
        svc.db.scalar.return_value = 1  # count
        svc.db.scalars.return_value.all.return_value = [ip]

        result = svc.list_institutional_perfs(ORG_ID)

        assert result.total >= 0


# ---------------------------------------------------------------------------
# create_for_cycle
# ---------------------------------------------------------------------------


class TestCreateForCycle:
    def test_initializes_criteria_from_templates(self) -> None:
        """criteria_scores is built from active templates for the institution type."""
        svc = make_service()

        templates = [
            make_template("Budget Execution", 30, 1),
            make_template("Service Delivery", 40, 2),
            make_template("Staff Performance", 30, 3),
        ]
        svc.db.scalars.return_value.all.return_value = templates

        result = svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        assert result.criteria_scores is not None
        assert len(result.criteria_scores) == 3

        names = [c["criteria"] for c in result.criteria_scores]
        assert "Budget Execution" in names
        assert "Service Delivery" in names
        assert "Staff Performance" in names

    def test_criteria_score_entries_have_expected_keys(self) -> None:
        """Each criterion entry has criteria, weight, target, achievement,
        raw_score and weighted_score keys."""
        svc = make_service()
        templates = [make_template("Policy Implementation", 100, 1)]
        svc.db.scalars.return_value.all.return_value = templates

        result = svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        entry = result.criteria_scores[0]
        for key in (
            "criteria",
            "weight",
            "target",
            "achievement",
            "raw_score",
            "weighted_score",
        ):
            assert key in entry, f"Missing key: {key}"

    def test_initial_score_fields_are_none(self) -> None:
        """target, achievement, raw_score, weighted_score all start as None."""
        svc = make_service()
        templates = [
            make_template("Governance", 50, 1),
            make_template("Finance", 50, 2),
        ]
        svc.db.scalars.return_value.all.return_value = templates

        result = svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        for entry in result.criteria_scores:
            assert entry["target"] is None
            assert entry["achievement"] is None
            assert entry["raw_score"] is None
            assert entry["weighted_score"] is None

    def test_status_is_draft(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = [
            make_template("Finance", 100, 1)
        ]

        result = svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        assert result.status == InstitutionalPerfStatus.DRAFT

    def test_department_id_set_when_provided(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = [
            make_template("Finance", 100, 1)
        ]

        result = svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            department_id=DEPT_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        assert result.department_id == DEPT_ID

    def test_db_add_and_flush_called(self) -> None:
        svc = make_service()
        svc.db.scalars.return_value.all.return_value = [
            make_template("Finance", 100, 1)
        ]

        svc.create_for_cycle(
            ORG_ID,
            cycle_id=CYCLE_ID,
            institution_type=InstitutionType.MINISTRY,
        )

        svc.db.add.assert_called_once()
        svc.db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# score_criteria
# ---------------------------------------------------------------------------


class TestScoreCriteria:
    def _make_scored_criteria(self) -> list[dict]:
        """Criteria input with target and achievement populated."""
        return [
            {
                "criteria": "Budget Execution",
                "weight": 40,
                "target": 100.0,
                "achievement": 95.0,
                "raw_score": None,
                "weighted_score": None,
            },
            {
                "criteria": "Service Delivery",
                "weight": 60,
                "target": 100.0,
                "achievement": 80.0,
                "raw_score": None,
                "weighted_score": None,
            },
        ]

    def test_sets_status_to_appraised(self) -> None:
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        result = svc.score_criteria(
            ORG_ID,
            INST_PERF_ID,
            criteria_scores=self._make_scored_criteria(),
        )

        assert result.status == InstitutionalPerfStatus.APPRAISED

    def test_calculates_composite_score(self) -> None:
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        result = svc.score_criteria(
            ORG_ID,
            INST_PERF_ID,
            criteria_scores=self._make_scored_criteria(),
        )

        assert result.composite_score is not None
        assert isinstance(result.composite_score, Decimal)
        assert Decimal("0") <= result.composite_score <= Decimal("100")

    def test_sets_rating_label(self) -> None:
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        result = svc.score_criteria(
            ORG_ID,
            INST_PERF_ID,
            criteria_scores=self._make_scored_criteria(),
        )

        assert result.rating_label is not None
        assert len(result.rating_label) > 0

    def test_criteria_without_target_or_achievement_skip_scoring(self) -> None:
        """Criteria missing target/achievement leave raw_score and weighted_score as None."""
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        criteria = [
            {
                "criteria": "Finance",
                "weight": 100,
                "target": None,
                "achievement": None,
                "raw_score": None,
                "weighted_score": None,
            }
        ]
        result = svc.score_criteria(ORG_ID, INST_PERF_ID, criteria_scores=criteria)

        entry = result.criteria_scores[0]
        assert entry["raw_score"] is None
        assert entry["weighted_score"] is None

    def test_weighted_scores_stored_on_criteria(self) -> None:
        """After scoring, raw_score and weighted_score are stored on each entry."""
        svc = make_service()
        ip = make_inst_perf()
        svc.db.scalar.return_value = ip

        result = svc.score_criteria(
            ORG_ID,
            INST_PERF_ID,
            criteria_scores=self._make_scored_criteria(),
        )

        for entry in result.criteria_scores:
            if entry["target"] is not None and entry["achievement"] is not None:
                assert entry["raw_score"] is not None
                assert entry["weighted_score"] is not None

    def test_raises_not_found_for_unknown_inst_perf(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(InstitutionalPerfNotFoundError):
            svc.score_criteria(ORG_ID, INST_PERF_ID, criteria_scores=[])


# ---------------------------------------------------------------------------
# reconcile_with_employee_ratings
# ---------------------------------------------------------------------------


class TestReconciliation:
    def test_saves_pre_reconciliation_score(self) -> None:
        """pre_reconciliation_composite is set to composite_score before any adjustment."""
        svc = make_service()
        original_score = Decimal("78.50")
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=original_score,
        )
        svc.db.scalar.return_value = ip

        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Reviewed by committee",
        )

        assert result.pre_reconciliation_composite == original_score

    def test_adjusts_composite_when_provided(self) -> None:
        """composite_score and rating_label are updated when adjusted_composite supplied."""
        svc = make_service()
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=Decimal("65.00"),
        )
        svc.db.scalar.return_value = ip

        adjusted = Decimal("72.00")
        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Adjusted after peer review",
            adjusted_composite=adjusted,
        )

        assert result.composite_score == adjusted
        assert result.rating_label is not None

    def test_composite_unchanged_when_no_adjustment(self) -> None:
        """composite_score is unchanged when adjusted_composite is not provided."""
        svc = make_service()
        original = Decimal("82.00")
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=original,
        )
        svc.db.scalar.return_value = ip

        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="No change",
        )

        assert result.composite_score == original

    def test_sets_is_reconciled_true(self) -> None:
        svc = make_service()
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=Decimal("70.00"),
        )
        svc.db.scalar.return_value = ip

        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Done",
        )

        assert result.is_reconciled is True

    def test_sets_reconciliation_metadata(self) -> None:
        svc = make_service()
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=Decimal("70.00"),
        )
        svc.db.scalar.return_value = ip

        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Final notes",
        )

        assert result.reconciled_by_id == RECONCILER_ID
        assert result.reconciliation_date == date.today()
        assert result.reconciliation_notes == "Final notes"

    def test_sets_status_to_reconciled(self) -> None:
        svc = make_service()
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=Decimal("70.00"),
        )
        svc.db.scalar.return_value = ip

        result = svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Done",
        )

        assert result.status == InstitutionalPerfStatus.RECONCILED

    def test_raises_not_found_for_unknown_inst_perf(self) -> None:
        svc = make_service()
        svc.db.scalar.return_value = None

        with pytest.raises(InstitutionalPerfNotFoundError):
            svc.reconcile_with_employee_ratings(
                ORG_ID,
                INST_PERF_ID,
                reconciled_by_id=RECONCILER_ID,
                notes="notes",
            )

    def test_db_flush_called(self) -> None:
        svc = make_service()
        ip = make_inst_perf(
            status=InstitutionalPerfStatus.APPRAISED,
            composite_score=Decimal("70.00"),
        )
        svc.db.scalar.return_value = ip

        svc.reconcile_with_employee_ratings(
            ORG_ID,
            INST_PERF_ID,
            reconciled_by_id=RECONCILER_ID,
            notes="Done",
        )

        svc.db.flush.assert_called()

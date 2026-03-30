"""
Tests for MonthlyReviewService — logic and validation.

Tests focus on validation methods and state transitions using
MagicMock for the DB session, following the contract_service test
pattern established in the PMS module.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.models.people.perf.monthly_review import MonthlyReview
from app.models.people.perf.pms_enums import MonthlyReviewStatus
from app.services.people.perf.monthly_review_service import (
    MonthlyReviewNotFoundError,
    MonthlyReviewService,
    MonthlyReviewServiceError,
    MonthlyReviewValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_service() -> MonthlyReviewService:
    db = MagicMock()
    return MonthlyReviewService(db)


def make_review(
    *,
    status: MonthlyReviewStatus = MonthlyReviewStatus.DRAFT,
    review_month: date | None = None,
) -> MagicMock:
    """Create a MagicMock MonthlyReview with sensible defaults."""
    r = MagicMock(spec=MonthlyReview)
    r.review_id = uuid.uuid4()
    r.organization_id = uuid.uuid4()
    r.employee_id = uuid.uuid4()
    r.reviewer_id = uuid.uuid4()
    r.contract_id = uuid.uuid4()
    r.review_month = review_month or date(2026, 3, 1)
    r.status = status
    r.objective_progress = None
    r.challenges = None
    r.support_required = None
    r.reviewer_feedback = None
    r.agreed_actions = None
    r.reviewer_signed_date = None
    r.employee_signed_date = None
    return r


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_not_found_is_service_error(self) -> None:
        err = MonthlyReviewNotFoundError(uuid.uuid4())
        assert isinstance(err, MonthlyReviewServiceError)

    def test_validation_is_service_error(self) -> None:
        err = MonthlyReviewValidationError("bad input")
        assert isinstance(err, MonthlyReviewServiceError)

    def test_not_found_message_contains_id(self) -> None:
        rid = uuid.uuid4()
        err = MonthlyReviewNotFoundError(rid)
        assert str(rid) in str(err)

    def test_validation_error_preserves_message(self) -> None:
        err = MonthlyReviewValidationError("specific problem")
        assert "specific problem" in str(err)


# ---------------------------------------------------------------------------
# get_review
# ---------------------------------------------------------------------------


class TestGetReview:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def test_returns_review_when_found(self) -> None:
        org_id = uuid.uuid4()
        review_id = uuid.uuid4()
        mock_review = make_review()
        mock_review.organization_id = org_id
        mock_review.review_id = review_id

        self.db.scalar.return_value = mock_review

        result = self.service.get_review(org_id, review_id)
        assert result is mock_review

    def test_raises_not_found_when_missing(self) -> None:
        self.db.scalar.return_value = None
        with pytest.raises(MonthlyReviewNotFoundError):
            self.service.get_review(uuid.uuid4(), uuid.uuid4())

    def test_not_found_error_has_correct_review_id(self) -> None:
        review_id = uuid.uuid4()
        self.db.scalar.return_value = None
        with pytest.raises(MonthlyReviewNotFoundError) as exc_info:
            self.service.get_review(uuid.uuid4(), review_id)
        assert exc_info.value.review_id == review_id


# ---------------------------------------------------------------------------
# create_review
# ---------------------------------------------------------------------------


class TestCreateReview:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.db.scalar.return_value = None  # no duplicate by default
        self.service = MonthlyReviewService(self.db)

    def test_rejects_non_first_of_month(self) -> None:
        with pytest.raises(MonthlyReviewValidationError, match="first day"):
            self.service.create_review(
                uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                review_month=date(2026, 3, 15),  # not the 1st
            )

    def test_accepts_first_of_month(self) -> None:
        """create_review should not raise for a date on the 1st."""
        added: list = []
        self.db.add.side_effect = lambda obj: added.append(obj)

        # No exception expected
        self.service.create_review(
            uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            review_month=date(2026, 3, 1),
        )

        assert len(added) == 1

    def test_new_review_has_draft_status(self) -> None:
        added: list = []
        self.db.add.side_effect = lambda obj: added.append(obj)

        self.service.create_review(
            uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            review_month=date(2026, 4, 1),
        )

        review = added[0]
        assert review.status == MonthlyReviewStatus.DRAFT

    def test_optional_fields_passed_through(self) -> None:
        added: list = []
        self.db.add.side_effect = lambda obj: added.append(obj)

        progress = [{"kra": "Finance", "score": 4}]
        self.service.create_review(
            uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            review_month=date(2026, 4, 1),
            objective_progress=progress,
            challenges="Resourcing",
            support_required="Budget approval",
        )

        review = added[0]
        assert review.objective_progress == progress
        assert review.challenges == "Resourcing"
        assert review.support_required == "Budget approval"

    def test_flush_is_called(self) -> None:
        self.service.create_review(
            uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            review_month=date(2026, 4, 1),
        )
        self.db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# submit_review
# ---------------------------------------------------------------------------


class TestSubmitReview:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def _setup_review(
        self, status: MonthlyReviewStatus = MonthlyReviewStatus.DRAFT
    ) -> MagicMock:
        review = make_review(status=status)
        self.db.scalar.return_value = review
        return review

    def test_submit_sets_status_to_submitted(self) -> None:
        review = self._setup_review()

        self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress={"kra1": "on track"},
        )

        assert review.status == MonthlyReviewStatus.SUBMITTED

    def test_submit_sets_reviewer_signed_date_to_today(self) -> None:
        review = self._setup_review()

        self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress={"kra1": "on track"},
        )

        assert review.reviewer_signed_date == date.today()

    def test_submit_updates_objective_progress(self) -> None:
        review = self._setup_review()
        progress = [{"kra": "Budget", "score": 3}]

        self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress=progress,
        )

        assert review.objective_progress == progress

    def test_submit_updates_optional_fields(self) -> None:
        review = self._setup_review()

        self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress={},
            challenges="Staffing",
            support_required="Training budget",
            reviewer_feedback="Good progress",
            agreed_actions="Monthly check-in",
        )

        assert review.challenges == "Staffing"
        assert review.support_required == "Training budget"
        assert review.reviewer_feedback == "Good progress"
        assert review.agreed_actions == "Monthly check-in"

    def test_submit_raises_not_found_for_missing_review(self) -> None:
        self.db.scalar.return_value = None

        with pytest.raises(MonthlyReviewNotFoundError):
            self.service.submit_review(
                uuid.uuid4(),
                uuid.uuid4(),
                objective_progress={},
            )

    def test_submit_calls_flush(self) -> None:
        review = self._setup_review()

        self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress={},
        )

        self.db.flush.assert_called()


# ---------------------------------------------------------------------------
# acknowledge_review
# ---------------------------------------------------------------------------


class TestAcknowledgeReview:
    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def _setup_review(
        self, status: MonthlyReviewStatus = MonthlyReviewStatus.SUBMITTED
    ) -> MagicMock:
        review = make_review(status=status)
        self.db.scalar.return_value = review
        return review

    def test_acknowledge_sets_status_to_acknowledged(self) -> None:
        review = self._setup_review()

        self.service.acknowledge_review(review.organization_id, review.review_id)

        assert review.status == MonthlyReviewStatus.ACKNOWLEDGED

    def test_acknowledge_sets_employee_signed_date_to_today(self) -> None:
        review = self._setup_review()

        self.service.acknowledge_review(review.organization_id, review.review_id)

        assert review.employee_signed_date == date.today()

    def test_acknowledge_raises_not_found_for_missing_review(self) -> None:
        self.db.scalar.return_value = None

        with pytest.raises(MonthlyReviewNotFoundError):
            self.service.acknowledge_review(uuid.uuid4(), uuid.uuid4())

    def test_acknowledge_calls_flush(self) -> None:
        review = self._setup_review()

        self.service.acknowledge_review(review.organization_id, review.review_id)

        self.db.flush.assert_called()

    def test_acknowledge_does_not_alter_reviewer_signed_date(self) -> None:
        review = self._setup_review()
        original_reviewer_date = date(2026, 3, 10)
        review.reviewer_signed_date = original_reviewer_date

        self.service.acknowledge_review(review.organization_id, review.review_id)

        # reviewer_signed_date should remain unchanged
        assert review.reviewer_signed_date == original_reviewer_date


# ---------------------------------------------------------------------------
# create_review — duplicate detection
# ---------------------------------------------------------------------------


class TestCreateReviewDuplicateDetection:
    """Test one-per-employee-per-month enforcement."""

    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def test_rejects_duplicate_review_for_same_month(self) -> None:
        """Creating a second review for same employee+month raises error."""
        existing = make_review(review_month=date(2026, 3, 1))
        # scalar() is called first for the duplicate check
        self.db.scalar.return_value = existing

        with pytest.raises(MonthlyReviewValidationError, match="already exists"):
            self.service.create_review(
                uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                review_month=date(2026, 3, 1),
            )

    def test_duplicate_error_mentions_month(self) -> None:
        """The validation error message includes the month name."""
        existing = make_review(review_month=date(2026, 3, 1))
        self.db.scalar.return_value = existing

        with pytest.raises(MonthlyReviewValidationError) as exc_info:
            self.service.create_review(
                uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                review_month=date(2026, 3, 1),
            )

        assert "March 2026" in str(exc_info.value)

    def test_allows_review_for_different_month(self) -> None:
        """Different month for same employee is OK — no error raised."""
        # No existing review for this month
        self.db.scalar.return_value = None
        added: list = []
        self.db.add.side_effect = lambda obj: added.append(obj)

        self.service.create_review(
            uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reviewer_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            review_month=date(2026, 4, 1),
        )

        assert len(added) == 1

    def test_does_not_add_to_db_when_duplicate(self) -> None:
        """db.add() must not be called when a duplicate is rejected."""
        existing = make_review(review_month=date(2026, 3, 1))
        self.db.scalar.return_value = existing

        with pytest.raises(MonthlyReviewValidationError):
            self.service.create_review(
                uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reviewer_id=uuid.uuid4(),
                contract_id=uuid.uuid4(),
                review_month=date(2026, 3, 1),
            )

        self.db.add.assert_not_called()


# ---------------------------------------------------------------------------
# submit_review — status guard
# ---------------------------------------------------------------------------


class TestSubmitReviewStatusGuard:
    """Test that submit_review enforces DRAFT-only precondition."""

    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def _setup_review(self, status: MonthlyReviewStatus) -> MagicMock:
        review = make_review(status=status)
        self.db.scalar.return_value = review
        return review

    def test_rejects_submit_from_submitted_status(self) -> None:
        """Cannot re-submit an already SUBMITTED review."""
        review = self._setup_review(MonthlyReviewStatus.SUBMITTED)

        with pytest.raises(MonthlyReviewValidationError):
            self.service.submit_review(
                review.organization_id,
                review.review_id,
                objective_progress={},
            )

    def test_rejects_submit_from_acknowledged_status(self) -> None:
        """Cannot submit an ACKNOWLEDGED review."""
        review = self._setup_review(MonthlyReviewStatus.ACKNOWLEDGED)

        with pytest.raises(MonthlyReviewValidationError):
            self.service.submit_review(
                review.organization_id,
                review.review_id,
                objective_progress={},
            )

    def test_submit_error_mentions_current_status(self) -> None:
        """Error message should include the current status value."""
        review = self._setup_review(MonthlyReviewStatus.SUBMITTED)

        with pytest.raises(MonthlyReviewValidationError) as exc_info:
            self.service.submit_review(
                review.organization_id,
                review.review_id,
                objective_progress={},
            )

        assert "SUBMITTED" in str(exc_info.value)

    def test_allows_submit_from_draft_status(self) -> None:
        """DRAFT → SUBMITTED transition is valid."""
        review = self._setup_review(MonthlyReviewStatus.DRAFT)

        result = self.service.submit_review(
            review.organization_id,
            review.review_id,
            objective_progress={"kra": "on track"},
        )

        assert result.status == MonthlyReviewStatus.SUBMITTED


# ---------------------------------------------------------------------------
# acknowledge_review — status guard
# ---------------------------------------------------------------------------


class TestAcknowledgeReviewStatusGuard:
    """Test that acknowledge_review enforces SUBMITTED-only precondition."""

    def setup_method(self) -> None:
        self.db = MagicMock()
        self.service = MonthlyReviewService(self.db)

    def _setup_review(self, status: MonthlyReviewStatus) -> MagicMock:
        review = make_review(status=status)
        self.db.scalar.return_value = review
        return review

    def test_rejects_acknowledge_from_draft_status(self) -> None:
        """Cannot acknowledge a DRAFT review."""
        review = self._setup_review(MonthlyReviewStatus.DRAFT)

        with pytest.raises(MonthlyReviewValidationError):
            self.service.acknowledge_review(review.organization_id, review.review_id)

    def test_rejects_acknowledge_from_acknowledged_status(self) -> None:
        """Cannot re-acknowledge an already ACKNOWLEDGED review."""
        review = self._setup_review(MonthlyReviewStatus.ACKNOWLEDGED)

        with pytest.raises(MonthlyReviewValidationError):
            self.service.acknowledge_review(review.organization_id, review.review_id)

    def test_acknowledge_error_mentions_current_status(self) -> None:
        """Error message includes the current status value."""
        review = self._setup_review(MonthlyReviewStatus.DRAFT)

        with pytest.raises(MonthlyReviewValidationError) as exc_info:
            self.service.acknowledge_review(review.organization_id, review.review_id)

        assert "DRAFT" in str(exc_info.value)

    def test_allows_acknowledge_from_submitted_status(self) -> None:
        """SUBMITTED → ACKNOWLEDGED is the valid transition."""
        review = self._setup_review(MonthlyReviewStatus.SUBMITTED)

        result = self.service.acknowledge_review(
            review.organization_id, review.review_id
        )

        assert result.status == MonthlyReviewStatus.ACKNOWLEDGED


# ---------------------------------------------------------------------------
# Status transition constants / enum sanity
# ---------------------------------------------------------------------------


class TestMonthlyReviewStatusEnum:
    def test_draft_value(self) -> None:
        assert MonthlyReviewStatus.DRAFT == "DRAFT"

    def test_submitted_value(self) -> None:
        assert MonthlyReviewStatus.SUBMITTED == "SUBMITTED"

    def test_acknowledged_value(self) -> None:
        assert MonthlyReviewStatus.ACKNOWLEDGED == "ACKNOWLEDGED"

    def test_all_statuses_are_strings(self) -> None:
        for status in MonthlyReviewStatus:
            assert isinstance(status, str)

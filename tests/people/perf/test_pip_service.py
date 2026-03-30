"""
Tests for PIPService — validation logic and status transitions.

Tests focus on business rules using MagicMock for the DB session.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.people.perf.pip_service import (
    PIPNotFoundError,
    PIPService,
    PIPServiceError,
    PIPStatusError,
    PIPValidationError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_service() -> PIPService:
    db = MagicMock()
    return PIPService(db)


def make_pip(
    *,
    status=None,
    extension_granted: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
    outcome=None,
) -> MagicMock:
    from app.models.people.perf.pip import PerformanceImprovementPlan
    from app.models.people.perf.pms_enums import PIPStatus

    pip = MagicMock(spec=PerformanceImprovementPlan)
    pip.pip_id = uuid.uuid4()
    pip.organization_id = uuid.uuid4()
    pip.status = status or PIPStatus.DRAFT
    pip.extension_granted = extension_granted
    pip.start_date = start_date or date(2026, 1, 1)
    pip.end_date = end_date or date(2026, 4, 1)
    pip.extension_end_date = None
    pip.extension_reason = None
    pip.outcome = outcome
    pip.outcome_date = None
    pip.outcome_notes = None
    pip.committee_referral_date = None
    pip.completion_letter_issued = False
    pip.review_intervals = None
    return pip


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_pip_not_found_is_pip_service_error(self) -> None:
        err = PIPNotFoundError(uuid.uuid4())
        assert isinstance(err, PIPServiceError)

    def test_pip_validation_is_pip_service_error(self) -> None:
        err = PIPValidationError("bad input")
        assert isinstance(err, PIPServiceError)

    def test_pip_status_is_pip_service_error(self) -> None:
        err = PIPStatusError("DRAFT", "CLOSED")
        assert isinstance(err, PIPServiceError)

    def test_not_found_message_contains_id(self) -> None:
        pip_id = uuid.uuid4()
        err = PIPNotFoundError(pip_id)
        assert str(pip_id) in str(err)

    def test_status_error_message_contains_states(self) -> None:
        err = PIPStatusError("DRAFT", "CLOSED")
        msg = str(err)
        assert "DRAFT" in msg
        assert "CLOSED" in msg


# ---------------------------------------------------------------------------
# TestPIPDurationValidation
# ---------------------------------------------------------------------------


class TestPIPDurationValidation:
    """Duration must not exceed 183 days (approx. 6 months)."""

    def test_rejects_duration_over_6_months(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        end = start + timedelta(days=184)  # 184 days — over limit
        with pytest.raises(PIPValidationError, match="183"):
            service._validate_duration(start, end)

    def test_accepts_6_month_duration(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        end = start + timedelta(days=183)  # exactly 183 days — allowed
        service._validate_duration(start, end)  # should not raise

    def test_accepts_duration_under_limit(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        end = start + timedelta(days=90)
        service._validate_duration(start, end)  # should not raise

    def test_rejects_end_before_start(self) -> None:
        service = make_service()
        start = date(2026, 3, 1)
        end = date(2026, 1, 1)
        with pytest.raises(PIPValidationError):
            service._validate_duration(start, end)

    def test_rejects_same_day_start_and_end(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        with pytest.raises(PIPValidationError):
            service._validate_duration(start, start)

    def test_boundary_183_days_accepted(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        end = start + timedelta(days=183)
        service._validate_duration(start, end)

    def test_boundary_184_days_rejected(self) -> None:
        service = make_service()
        start = date(2026, 1, 1)
        end = start + timedelta(days=184)
        with pytest.raises(PIPValidationError):
            service._validate_duration(start, end)


# ---------------------------------------------------------------------------
# TestPIPExtension
# ---------------------------------------------------------------------------


class TestPIPExtension:
    """Extension rules: max one extension of up to 92 days from current end_date."""

    def test_rejects_second_extension(self) -> None:
        db = MagicMock()
        service = PIPService(db)

        from app.models.people.perf.pms_enums import PIPStatus

        pip = make_pip(status=PIPStatus.EXTENDED, extension_granted=True)
        pip.end_date = date(2026, 4, 1)
        db.scalar.return_value = pip

        with pytest.raises(PIPValidationError, match="[Ee]xtension"):
            service.grant_extension(
                pip.organization_id,
                pip.pip_id,
                new_end_date=date(2026, 5, 1),
                reason="More time needed",
            )

    def test_rejects_extension_over_3_months(self) -> None:
        db = MagicMock()
        service = PIPService(db)

        from app.models.people.perf.pms_enums import PIPStatus

        pip = make_pip(status=PIPStatus.ACTIVE, extension_granted=False)
        pip.end_date = date(2026, 4, 1)
        db.scalar.return_value = pip

        # 93 days beyond current end_date — over the 92-day limit
        new_end = pip.end_date + timedelta(days=93)
        with pytest.raises(PIPValidationError, match="92"):
            service.grant_extension(
                pip.organization_id,
                pip.pip_id,
                new_end_date=new_end,
                reason="Excess extension",
            )

    def test_accepts_valid_extension(self) -> None:
        db = MagicMock()
        service = PIPService(db)

        from app.models.people.perf.pms_enums import PIPStatus
        from app.models.people.perf.pms_enums import PIPStatus as S

        pip = make_pip(status=PIPStatus.ACTIVE, extension_granted=False)
        pip.end_date = date(2026, 4, 1)
        db.scalar.return_value = pip

        new_end = pip.end_date + timedelta(days=60)  # 60 days — valid
        result = service.grant_extension(
            pip.organization_id,
            pip.pip_id,
            new_end_date=new_end,
            reason="Performance improving",
        )

        assert result.extension_granted is True
        assert result.extension_end_date == new_end
        assert result.status == S.EXTENDED

    def test_accepts_extension_of_exactly_92_days(self) -> None:
        db = MagicMock()
        service = PIPService(db)

        from app.models.people.perf.pms_enums import PIPStatus

        pip = make_pip(status=PIPStatus.ACTIVE, extension_granted=False)
        pip.end_date = date(2026, 4, 1)
        db.scalar.return_value = pip

        new_end = pip.end_date + timedelta(days=92)  # exactly 92 — allowed
        result = service.grant_extension(
            pip.organization_id,
            pip.pip_id,
            new_end_date=new_end,
            reason="Boundary test",
        )

        assert result.extension_granted is True


# ---------------------------------------------------------------------------
# TestGetPIP
# ---------------------------------------------------------------------------


class TestGetPIP:
    def test_returns_pip_when_found(self) -> None:
        from app.models.people.perf.pip import PerformanceImprovementPlan

        db = MagicMock()
        service = PIPService(db)
        org_id = uuid.uuid4()
        pip_id = uuid.uuid4()

        mock_pip = MagicMock(spec=PerformanceImprovementPlan)
        mock_pip.organization_id = org_id
        mock_pip.pip_id = pip_id
        db.scalar.return_value = mock_pip

        result = service.get_pip(org_id, pip_id)
        assert result is mock_pip

    def test_raises_not_found_when_missing(self) -> None:
        db = MagicMock()
        service = PIPService(db)
        db.scalar.return_value = None

        with pytest.raises(PIPNotFoundError):
            service.get_pip(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# TestActivatePIP
# ---------------------------------------------------------------------------


class TestActivatePIP:
    def test_draft_transitions_to_active(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.DRAFT)
        db.scalar.return_value = pip

        result = service.activate_pip(pip.organization_id, pip.pip_id)
        assert result.status == PIPStatus.ACTIVE

    def test_non_draft_raises_status_error(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        db.scalar.return_value = pip

        with pytest.raises(PIPStatusError):
            service.activate_pip(pip.organization_id, pip.pip_id)


# ---------------------------------------------------------------------------
# TestRecordReview
# ---------------------------------------------------------------------------


class TestRecordReview:
    def test_appends_review_to_empty_list(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        pip.review_intervals = None
        db.scalar.return_value = pip

        service.record_review(
            pip.organization_id,
            pip.pip_id,
            review_date=date(2026, 2, 1),
            notes="Good progress noted",
            progress_status="ON_TRACK",
        )

        assert isinstance(pip.review_intervals, list)
        assert len(pip.review_intervals) == 1
        assert pip.review_intervals[0]["notes"] == "Good progress noted"
        assert pip.review_intervals[0]["progress_status"] == "ON_TRACK"

    def test_appends_review_to_existing_list(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        pip.review_intervals = [{"review_date": "2026-01-15", "notes": "Initial"}]
        db.scalar.return_value = pip

        service.record_review(
            pip.organization_id,
            pip.pip_id,
            review_date=date(2026, 2, 15),
            notes="Second check",
            progress_status="BEHIND",
        )

        assert len(pip.review_intervals) == 2


# ---------------------------------------------------------------------------
# TestCompletePIP
# ---------------------------------------------------------------------------


class TestCompletePIP:
    def test_satisfactory_outcome_sets_improved_status(self) -> None:
        from app.models.people.perf.pms_enums import PIPOutcome, PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        db.scalar.return_value = pip

        service.complete_pip(
            pip.organization_id,
            pip.pip_id,
            outcome=PIPOutcome.SATISFACTORY,
            notes="Employee met all targets",
        )

        assert pip.status == PIPStatus.IMPROVED
        assert pip.outcome == PIPOutcome.SATISFACTORY
        assert pip.outcome_date == date.today()

    def test_unsatisfactory_outcome_sets_escalated_status(self) -> None:
        from app.models.people.perf.pms_enums import PIPOutcome, PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        db.scalar.return_value = pip

        service.complete_pip(
            pip.organization_id,
            pip.pip_id,
            outcome=PIPOutcome.UNSATISFACTORY,
            notes="No improvement observed",
        )

        assert pip.status == PIPStatus.ESCALATED
        assert pip.outcome == PIPOutcome.UNSATISFACTORY
        assert pip.committee_referral_date == date.today()

    def test_complete_sets_outcome_notes(self) -> None:
        from app.models.people.perf.pms_enums import PIPOutcome, PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE)
        db.scalar.return_value = pip

        service.complete_pip(
            pip.organization_id,
            pip.pip_id,
            outcome=PIPOutcome.SATISFACTORY,
            notes="Great improvement",
        )

        assert pip.outcome_notes == "Great improvement"


# ---------------------------------------------------------------------------
# TestIssueCompletionLetter
# ---------------------------------------------------------------------------


class TestIssueCompletionLetter:
    def test_sets_completion_letter_issued_for_satisfactory(self) -> None:
        from app.models.people.perf.pms_enums import PIPOutcome, PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.IMPROVED, outcome=PIPOutcome.SATISFACTORY)
        pip.completion_letter_issued = False
        db.scalar.return_value = pip

        service.issue_completion_letter(pip.organization_id, pip.pip_id)
        assert pip.completion_letter_issued is True

    def test_raises_validation_error_for_unsatisfactory(self) -> None:
        from app.models.people.perf.pms_enums import PIPOutcome, PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ESCALATED, outcome=PIPOutcome.UNSATISFACTORY)
        db.scalar.return_value = pip

        with pytest.raises(PIPValidationError, match="(?i)satisfactory"):
            service.issue_completion_letter(pip.organization_id, pip.pip_id)

    def test_raises_validation_error_when_no_outcome(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        pip = make_pip(status=PIPStatus.ACTIVE, outcome=None)
        db.scalar.return_value = pip

        with pytest.raises(PIPValidationError):
            service.issue_completion_letter(pip.organization_id, pip.pip_id)


# ---------------------------------------------------------------------------
# TestCreatePIP
# ---------------------------------------------------------------------------


class TestCreatePIP:
    def test_create_pip_rejects_duration_over_183_days(self) -> None:
        db = MagicMock()
        service = PIPService(db)
        org_id = uuid.uuid4()
        start = date(2026, 1, 1)
        end = start + timedelta(days=184)

        with pytest.raises(PIPValidationError, match="183"):
            service.create_pip(
                org_id,
                employee_id=uuid.uuid4(),
                supervisor_id=uuid.uuid4(),
                hr_officer_id=uuid.uuid4(),
                pip_code="PIP-2026-001",
                start_date=start,
                end_date=end,
                reason="Missed targets",
                cause_category="SKILLS",
                improvement_areas=[{"area": "Reporting", "target": "On time"}],
            )

    def test_create_pip_returns_draft_pip(self) -> None:
        from app.models.people.perf.pms_enums import PIPStatus

        db = MagicMock()
        service = PIPService(db)
        org_id = uuid.uuid4()
        start = date(2026, 1, 1)
        end = start + timedelta(days=90)

        added: list = []
        db.add.side_effect = lambda obj: added.append(obj)

        result = service.create_pip(
            org_id,
            employee_id=uuid.uuid4(),
            supervisor_id=uuid.uuid4(),
            hr_officer_id=uuid.uuid4(),
            pip_code="PIP-2026-001",
            start_date=start,
            end_date=end,
            reason="Missed targets",
            cause_category="SKILLS",
            improvement_areas=[{"area": "Reporting", "target": "On time"}],
        )

        assert result.status == PIPStatus.DRAFT
        assert len(added) == 1
        db.flush.assert_called_once()

"""
Tests for AppraisalAppealService — status transitions and business logic.

Uses MagicMock for the DB session to keep tests fast and isolated.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.people.perf.pms_enums import AppealDecision, AppealStatus
from app.services.people.perf.appeal_service import (
    AppealNotFoundError,
    AppealServiceError,
    AppealValidationError,
    AppraisalAppealService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_service() -> AppraisalAppealService:
    db = MagicMock()
    return AppraisalAppealService(db)


def make_appeal(
    *,
    status: AppealStatus = AppealStatus.FILED,
    org_id: uuid.UUID | None = None,
    appeal_id: uuid.UUID | None = None,
    appraisal_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
) -> MagicMock:
    from app.models.people.perf.appraisal_appeal import AppraisalAppeal

    a = MagicMock(spec=AppraisalAppeal)
    a.appeal_id = appeal_id or uuid.uuid4()
    a.organization_id = org_id or uuid.uuid4()
    a.appraisal_id = appraisal_id or uuid.uuid4()
    a.employee_id = employee_id or uuid.uuid4()
    a.status = status
    a.mediation_date = None
    a.mediation_outcome = None
    a.mediation_resolved = False
    a.committee_referral_date = None
    a.committee_hearing_date = None
    a.committee_decision = None
    a.committee_notes = None
    a.adjusted_rating = None
    a.resolution_date = None
    a.communicated_date = None
    a.mediator_id = None
    return a


# ---------------------------------------------------------------------------
# Error class hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    def test_appeal_not_found_is_appeal_service_error(self) -> None:
        err = AppealNotFoundError(uuid.uuid4())
        assert isinstance(err, AppealServiceError)

    def test_appeal_validation_is_appeal_service_error(self) -> None:
        err = AppealValidationError("bad input")
        assert isinstance(err, AppealServiceError)

    def test_not_found_message_contains_id(self) -> None:
        aid = uuid.uuid4()
        err = AppealNotFoundError(aid)
        assert str(aid) in str(err)

    def test_validation_error_preserves_message(self) -> None:
        err = AppealValidationError("duplicate appeal")
        assert "duplicate appeal" in str(err)


# ---------------------------------------------------------------------------
# get_appeal
# ---------------------------------------------------------------------------


class TestGetAppeal:
    def test_returns_appeal_when_found(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal()
        db.scalar.return_value = appeal

        result = service.get_appeal(appeal.organization_id, appeal.appeal_id)

        assert result is appeal

    def test_raises_not_found_when_missing(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        db.scalar.return_value = None

        with pytest.raises(AppealNotFoundError):
            service.get_appeal(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# file_appeal
# ---------------------------------------------------------------------------


class TestFileAppeal:
    def _make_service_with_no_existing_appeal_and_no_appraisal(self) -> AppraisalAppealService:
        """Service whose DB returns None for both existing appeal check and appraisal fetch."""
        db = MagicMock()
        db.scalar.return_value = None
        return AppraisalAppealService(db)

    def test_file_creates_with_filed_status(self) -> None:
        """Filing an appeal creates it with FILED status."""
        service = self._make_service_with_no_existing_appeal_and_no_appraisal()
        org_id = uuid.uuid4()
        appraisal_id = uuid.uuid4()
        employee_id = uuid.uuid4()

        added = []
        service.db.add.side_effect = lambda obj: added.append(obj)

        appeal = service.file_appeal(
            org_id,
            appraisal_id=appraisal_id,
            employee_id=employee_id,
            reason="My rating was unfair.",
        )

        assert appeal.status == AppealStatus.FILED
        assert appeal.organization_id == org_id
        assert appeal.appraisal_id == appraisal_id
        assert appeal.employee_id == employee_id
        assert appeal.reason == "My rating was unfair."

    def test_file_defaults_filed_date_to_today(self) -> None:
        service = self._make_service_with_no_existing_appeal_and_no_appraisal()

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="Rating inconsistent.",
        )

        assert appeal.filed_date == date.today()

    def test_file_accepts_explicit_filed_date(self) -> None:
        service = self._make_service_with_no_existing_appeal_and_no_appraisal()
        explicit_date = date(2026, 2, 15)

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="Rating inconsistent.",
            filed_date=explicit_date,
        )

        assert appeal.filed_date == explicit_date

    def test_file_stores_requested_outcome(self) -> None:
        service = self._make_service_with_no_existing_appeal_and_no_appraisal()

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="Bad score.",
            requested_outcome="Upgrade to rating 4.",
        )

        assert appeal.requested_outcome == "Upgrade to rating 4."

    def test_file_raises_if_duplicate_open_appeal(self) -> None:
        """Filing raises AppealValidationError if an open appeal already exists."""
        db = MagicMock()
        service = AppraisalAppealService(db)

        existing_appeal = make_appeal(status=AppealStatus.UNDER_MEDIATION)
        # First scalar call returns an existing appeal (duplicate check)
        db.scalar.return_value = existing_appeal

        with pytest.raises(AppealValidationError, match="already exists"):
            service.file_appeal(
                uuid.uuid4(),
                appraisal_id=uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reason="My rating was unfair.",
            )

    def test_file_raises_if_outside_5_working_day_window(self) -> None:
        """Filing raises AppealValidationError when filed more than 5 working days after completion."""
        from app.models.people.perf.appraisal import Appraisal

        db = MagicMock()
        service = AppraisalAppealService(db)

        # completed on a Monday; filing on the following Wednesday = 8 working days later
        completion_date = date(2026, 2, 2)   # Monday
        filed_date = date(2026, 2, 11)        # Wednesday (7 working days later: T W Th F M T W)

        mock_appraisal = MagicMock(spec=Appraisal)
        mock_appraisal.completed_on = completion_date

        # First scalar call: no duplicate appeal; second: returns appraisal
        db.scalar.side_effect = [None, mock_appraisal]

        with pytest.raises(AppealValidationError, match="working days"):
            service.file_appeal(
                uuid.uuid4(),
                appraisal_id=uuid.uuid4(),
                employee_id=uuid.uuid4(),
                reason="Late appeal attempt.",
                filed_date=filed_date,
            )

    def test_file_allows_appeal_within_5_working_days(self) -> None:
        """Filing within the window succeeds."""
        from app.models.people.perf.appraisal import Appraisal

        db = MagicMock()
        service = AppraisalAppealService(db)

        completion_date = date(2026, 2, 2)   # Monday
        filed_date = date(2026, 2, 6)         # Friday — 5 working days inclusive

        mock_appraisal = MagicMock(spec=Appraisal)
        mock_appraisal.completed_on = completion_date

        db.scalar.side_effect = [None, mock_appraisal]

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="Valid filing.",
            filed_date=filed_date,
        )

        assert appeal.status == AppealStatus.FILED

    def test_file_skips_window_check_if_appraisal_not_found(self) -> None:
        """If appraisal record not found, window validation is skipped."""
        db = MagicMock()
        service = AppraisalAppealService(db)

        # No duplicate, no appraisal record
        db.scalar.side_effect = [None, None]

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="No appraisal record, still allow filing.",
            filed_date=date(2026, 6, 1),
        )

        assert appeal.status == AppealStatus.FILED

    def test_file_skips_window_check_if_appraisal_not_completed(self) -> None:
        """If appraisal has no completed_on date, window validation is skipped."""
        from app.models.people.perf.appraisal import Appraisal

        db = MagicMock()
        service = AppraisalAppealService(db)

        mock_appraisal = MagicMock(spec=Appraisal)
        mock_appraisal.completed_on = None

        db.scalar.side_effect = [None, mock_appraisal]

        appeal = service.file_appeal(
            uuid.uuid4(),
            appraisal_id=uuid.uuid4(),
            employee_id=uuid.uuid4(),
            reason="Appraisal not yet completed.",
        )

        assert appeal.status == AppealStatus.FILED


# ---------------------------------------------------------------------------
# assign_mediator
# ---------------------------------------------------------------------------


class TestAssignMediator:
    def test_sets_mediator_and_status(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal()
        mediator_id = uuid.uuid4()
        db.scalar.return_value = appeal

        result = service.assign_mediator(
            appeal.organization_id, appeal.appeal_id, mediator_id=mediator_id
        )

        assert result.mediator_id == mediator_id
        assert result.status == AppealStatus.UNDER_MEDIATION

    def test_raises_not_found_if_missing(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        db.scalar.return_value = None

        with pytest.raises(AppealNotFoundError):
            service.assign_mediator(uuid.uuid4(), uuid.uuid4(), mediator_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# record_mediation_outcome — status transitions
# ---------------------------------------------------------------------------


class TestMediationOutcome:
    def test_mediation_resolved_sets_resolved(self) -> None:
        """When resolved=True, status becomes RESOLVED with resolution_date=today."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.UNDER_MEDIATION)
        db.scalar.return_value = appeal

        result = service.record_mediation_outcome(
            appeal.organization_id,
            appeal.appeal_id,
            outcome="Both parties agreed to revised rating.",
            resolved=True,
        )

        assert result.status == AppealStatus.RESOLVED
        assert result.resolution_date == date.today()
        assert result.mediation_date == date.today()
        assert result.mediation_outcome == "Both parties agreed to revised rating."
        assert result.mediation_resolved is True

    def test_mediation_unresolved_escalates_to_committee(self) -> None:
        """When resolved=False, status becomes REFERRED_TO_COMMITTEE."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.UNDER_MEDIATION)
        db.scalar.return_value = appeal

        result = service.record_mediation_outcome(
            appeal.organization_id,
            appeal.appeal_id,
            outcome="No agreement reached.",
            resolved=False,
        )

        assert result.status == AppealStatus.REFERRED_TO_COMMITTEE
        assert result.committee_referral_date == date.today()
        assert result.resolution_date is None

    def test_mediation_unresolved_does_not_set_resolution_date(self) -> None:
        """Escalated appeals do not get a resolution_date."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.UNDER_MEDIATION)
        db.scalar.return_value = appeal

        service.record_mediation_outcome(
            appeal.organization_id,
            appeal.appeal_id,
            outcome="Escalating.",
            resolved=False,
        )

        assert appeal.resolution_date is None

    def test_raises_not_found_if_missing(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        db.scalar.return_value = None

        with pytest.raises(AppealNotFoundError):
            service.record_mediation_outcome(
                uuid.uuid4(), uuid.uuid4(), outcome="irrelevant", resolved=True
            )


# ---------------------------------------------------------------------------
# record_committee_decision — status transitions
# ---------------------------------------------------------------------------


class TestCommitteeDecision:
    def test_committee_decision_resolves(self) -> None:
        """Committee decision sets RESOLVED status and resolution_date."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        result = service.record_committee_decision(
            appeal.organization_id,
            appeal.appeal_id,
            decision=AppealDecision.DISMISSED,
            notes="Rating was fair per evaluation criteria.",
        )

        assert result.status == AppealStatus.RESOLVED
        assert result.resolution_date == date.today()
        assert result.committee_hearing_date == date.today()
        assert result.committee_decision == AppealDecision.DISMISSED
        assert result.committee_notes == "Rating was fair per evaluation criteria."

    def test_upheld_sets_adjusted_rating(self) -> None:
        """UPHELD decision records the adjusted_rating."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        result = service.record_committee_decision(
            appeal.organization_id,
            appeal.appeal_id,
            decision=AppealDecision.UPHELD,
            notes="Rating did not reflect actual output.",
            adjusted_rating=4,
        )

        assert result.adjusted_rating == 4
        assert result.status == AppealStatus.RESOLVED

    def test_partially_upheld_sets_adjusted_rating(self) -> None:
        """PARTIALLY_UPHELD decision also records the adjusted_rating."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        result = service.record_committee_decision(
            appeal.organization_id,
            appeal.appeal_id,
            decision=AppealDecision.PARTIALLY_UPHELD,
            notes="Some KPIs were misscored.",
            adjusted_rating=3,
        )

        assert result.adjusted_rating == 3

    def test_dismissed_does_not_require_adjusted_rating(self) -> None:
        """DISMISSED decision does not require adjusted_rating."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        result = service.record_committee_decision(
            appeal.organization_id,
            appeal.appeal_id,
            decision=AppealDecision.DISMISSED,
            notes="No grounds found.",
        )

        assert result.status == AppealStatus.RESOLVED

    def test_upheld_without_adjusted_rating_raises(self) -> None:
        """UPHELD without adjusted_rating raises AppealValidationError."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        with pytest.raises(AppealValidationError, match="adjusted_rating"):
            service.record_committee_decision(
                appeal.organization_id,
                appeal.appeal_id,
                decision=AppealDecision.UPHELD,
                notes="Upheld but forgot to pass adjusted_rating.",
            )

    def test_partially_upheld_without_adjusted_rating_raises(self) -> None:
        """PARTIALLY_UPHELD without adjusted_rating raises AppealValidationError."""
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.REFERRED_TO_COMMITTEE)
        db.scalar.return_value = appeal

        with pytest.raises(AppealValidationError, match="adjusted_rating"):
            service.record_committee_decision(
                appeal.organization_id,
                appeal.appeal_id,
                decision=AppealDecision.PARTIALLY_UPHELD,
                notes="Partially upheld but no rating given.",
            )

    def test_raises_not_found_if_missing(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        db.scalar.return_value = None

        with pytest.raises(AppealNotFoundError):
            service.record_committee_decision(
                uuid.uuid4(),
                uuid.uuid4(),
                decision=AppealDecision.DISMISSED,
                notes="irrelevant",
            )


# ---------------------------------------------------------------------------
# communicate_decision
# ---------------------------------------------------------------------------


class TestCommunicateDecision:
    def test_sets_communicated_date_to_today(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        appeal = make_appeal(status=AppealStatus.RESOLVED)
        db.scalar.return_value = appeal

        result = service.communicate_decision(appeal.organization_id, appeal.appeal_id)

        assert result.communicated_date == date.today()

    def test_raises_not_found_if_missing(self) -> None:
        db = MagicMock()
        service = AppraisalAppealService(db)
        db.scalar.return_value = None

        with pytest.raises(AppealNotFoundError):
            service.communicate_decision(uuid.uuid4(), uuid.uuid4())


# ---------------------------------------------------------------------------
# get_overdue_appeals
# ---------------------------------------------------------------------------


class TestGetOverdueAppeals:
    def test_returns_empty_when_before_deadline(self) -> None:
        """Returns empty list when today is on or before Feb 28."""
        db = MagicMock()
        service = AppraisalAppealService(db)

        with patch("app.services.people.perf.appeal_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 20)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            result = service.get_overdue_appeals(uuid.uuid4())

        assert result == []
        db.scalars.assert_not_called()

    def test_returns_unresolved_appeals_after_deadline(self) -> None:
        """Returns unresolved appeals when today is past Feb 28."""
        db = MagicMock()
        service = AppraisalAppealService(db)

        overdue_appeals = [make_appeal(status=AppealStatus.FILED)]
        db.scalars.return_value.all.return_value = overdue_appeals

        with patch("app.services.people.perf.appeal_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 5)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            result = service.get_overdue_appeals(uuid.uuid4())

        assert result == overdue_appeals

    def test_returns_empty_on_deadline_day(self) -> None:
        """Returns empty list when today is exactly Feb 28 (not yet overdue)."""
        db = MagicMock()
        service = AppraisalAppealService(db)

        with patch("app.services.people.perf.appeal_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

            result = service.get_overdue_appeals(uuid.uuid4())

        assert result == []


# ---------------------------------------------------------------------------
# list_appeals
# ---------------------------------------------------------------------------


class TestListAppeals:
    def test_returns_paginated_result(self) -> None:
        from app.services.common import PaginatedResult

        db = MagicMock()
        service = AppraisalAppealService(db)

        # paginate is called via db.scalar and db.scalars — mock the result
        with patch(
            "app.services.people.perf.appeal_service.paginate"
        ) as mock_paginate:
            expected = PaginatedResult(items=[], total=0, offset=0, limit=50)
            mock_paginate.return_value = expected

            result = service.list_appeals(uuid.uuid4())

        assert result is expected
        assert mock_paginate.called

    def test_no_error_with_all_filters(self) -> None:
        """list_appeals accepts all optional filter params without raising."""
        from app.services.common import PaginatedResult, PaginationParams

        db = MagicMock()
        service = AppraisalAppealService(db)

        with patch("app.services.people.perf.appeal_service.paginate") as mock_paginate:
            mock_paginate.return_value = PaginatedResult(items=[], total=0, offset=0, limit=25)

            result = service.list_appeals(
                uuid.uuid4(),
                status=AppealStatus.FILED,
                employee_id=uuid.uuid4(),
                search="unfair",
                pagination=PaginationParams(offset=0, limit=25),
            )

        assert result.total == 0

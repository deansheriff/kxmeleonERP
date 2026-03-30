"""
Test suite for PMS (Performance Management System) enums.

Verifies all enum values exist and have correct string representations.
"""

from app.models.people.perf.pms_enums import (
    AppealDecision,
    AppealStatus,
    CommitteeDecision,
    ConfirmationRecommendation,
    ContractStatus,
    ContractType,
    InstitutionalPerfStatus,
    InstitutionType,
    MonthlyReviewStatus,
    OutcomeActionStatus,
    OutcomeActionType,
    PIPCauseCategory,
    PIPOutcome,
    PIPStatus,
)


class TestContractStatus:
    """ContractStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required contract status values exist."""
        assert hasattr(ContractStatus, "DRAFT")
        assert hasattr(ContractStatus, "PENDING_SIGNATURE")
        assert hasattr(ContractStatus, "ACTIVE")
        assert hasattr(ContractStatus, "AMENDED")
        assert hasattr(ContractStatus, "COMPLETED")
        assert hasattr(ContractStatus, "CANCELLED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert ContractStatus.DRAFT.value == "DRAFT"
        assert ContractStatus.PENDING_SIGNATURE.value == "PENDING_SIGNATURE"
        assert ContractStatus.ACTIVE.value == "ACTIVE"
        assert ContractStatus.AMENDED.value == "AMENDED"
        assert ContractStatus.COMPLETED.value == "COMPLETED"
        assert ContractStatus.CANCELLED.value == "CANCELLED"

    def test_is_str_enum(self):
        """Verify ContractStatus is a string enum."""
        assert isinstance(ContractStatus.DRAFT, str)


class TestContractType:
    """ContractType enum tests."""

    def test_all_values_exist(self):
        """Verify all required contract type values exist."""
        assert hasattr(ContractType, "MINISTERIAL")
        assert hasattr(ContractType, "DEPARTMENTAL")
        assert hasattr(ContractType, "INDIVIDUAL")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert ContractType.MINISTERIAL.value == "MINISTERIAL"
        assert ContractType.DEPARTMENTAL.value == "DEPARTMENTAL"
        assert ContractType.INDIVIDUAL.value == "INDIVIDUAL"

    def test_is_str_enum(self):
        """Verify ContractType is a string enum."""
        assert isinstance(ContractType.MINISTERIAL, str)


class TestMonthlyReviewStatus:
    """MonthlyReviewStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required monthly review status values exist."""
        assert hasattr(MonthlyReviewStatus, "DRAFT")
        assert hasattr(MonthlyReviewStatus, "SUBMITTED")
        assert hasattr(MonthlyReviewStatus, "ACKNOWLEDGED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert MonthlyReviewStatus.DRAFT.value == "DRAFT"
        assert MonthlyReviewStatus.SUBMITTED.value == "SUBMITTED"
        assert MonthlyReviewStatus.ACKNOWLEDGED.value == "ACKNOWLEDGED"

    def test_is_str_enum(self):
        """Verify MonthlyReviewStatus is a string enum."""
        assert isinstance(MonthlyReviewStatus.DRAFT, str)


class TestPIPStatus:
    """PIPStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required PIP status values exist."""
        assert hasattr(PIPStatus, "DRAFT")
        assert hasattr(PIPStatus, "ACTIVE")
        assert hasattr(PIPStatus, "UNDER_REVIEW")
        assert hasattr(PIPStatus, "IMPROVED")
        assert hasattr(PIPStatus, "EXTENDED")
        assert hasattr(PIPStatus, "ESCALATED")
        assert hasattr(PIPStatus, "CLOSED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert PIPStatus.DRAFT.value == "DRAFT"
        assert PIPStatus.ACTIVE.value == "ACTIVE"
        assert PIPStatus.UNDER_REVIEW.value == "UNDER_REVIEW"
        assert PIPStatus.IMPROVED.value == "IMPROVED"
        assert PIPStatus.EXTENDED.value == "EXTENDED"
        assert PIPStatus.ESCALATED.value == "ESCALATED"
        assert PIPStatus.CLOSED.value == "CLOSED"

    def test_is_str_enum(self):
        """Verify PIPStatus is a string enum."""
        assert isinstance(PIPStatus.DRAFT, str)


class TestPIPCauseCategory:
    """PIPCauseCategory enum tests."""

    def test_all_values_exist(self):
        """Verify all required PIP cause category values exist."""
        assert hasattr(PIPCauseCategory, "CLARITY")
        assert hasattr(PIPCauseCategory, "SKILLS")
        assert hasattr(PIPCauseCategory, "COMMITMENT")
        assert hasattr(PIPCauseCategory, "HEALTH")
        assert hasattr(PIPCauseCategory, "PERSONAL")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert PIPCauseCategory.CLARITY.value == "CLARITY"
        assert PIPCauseCategory.SKILLS.value == "SKILLS"
        assert PIPCauseCategory.COMMITMENT.value == "COMMITMENT"
        assert PIPCauseCategory.HEALTH.value == "HEALTH"
        assert PIPCauseCategory.PERSONAL.value == "PERSONAL"

    def test_is_str_enum(self):
        """Verify PIPCauseCategory is a string enum."""
        assert isinstance(PIPCauseCategory.CLARITY, str)


class TestPIPOutcome:
    """PIPOutcome enum tests."""

    def test_all_values_exist(self):
        """Verify all required PIP outcome values exist."""
        assert hasattr(PIPOutcome, "SATISFACTORY")
        assert hasattr(PIPOutcome, "UNSATISFACTORY")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert PIPOutcome.SATISFACTORY.value == "SATISFACTORY"
        assert PIPOutcome.UNSATISFACTORY.value == "UNSATISFACTORY"

    def test_is_str_enum(self):
        """Verify PIPOutcome is a string enum."""
        assert isinstance(PIPOutcome.SATISFACTORY, str)


class TestAppealStatus:
    """AppealStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required appeal status values exist."""
        assert hasattr(AppealStatus, "FILED")
        assert hasattr(AppealStatus, "UNDER_MEDIATION")
        assert hasattr(AppealStatus, "REFERRED_TO_COMMITTEE")
        assert hasattr(AppealStatus, "RESOLVED")
        assert hasattr(AppealStatus, "DISMISSED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert AppealStatus.FILED.value == "FILED"
        assert AppealStatus.UNDER_MEDIATION.value == "UNDER_MEDIATION"
        assert AppealStatus.REFERRED_TO_COMMITTEE.value == "REFERRED_TO_COMMITTEE"
        assert AppealStatus.RESOLVED.value == "RESOLVED"
        assert AppealStatus.DISMISSED.value == "DISMISSED"

    def test_is_str_enum(self):
        """Verify AppealStatus is a string enum."""
        assert isinstance(AppealStatus.FILED, str)


class TestAppealDecision:
    """AppealDecision enum tests."""

    def test_all_values_exist(self):
        """Verify all required appeal decision values exist."""
        assert hasattr(AppealDecision, "UPHELD")
        assert hasattr(AppealDecision, "PARTIALLY_UPHELD")
        assert hasattr(AppealDecision, "DISMISSED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert AppealDecision.UPHELD.value == "UPHELD"
        assert AppealDecision.PARTIALLY_UPHELD.value == "PARTIALLY_UPHELD"
        assert AppealDecision.DISMISSED.value == "DISMISSED"

    def test_is_str_enum(self):
        """Verify AppealDecision is a string enum."""
        assert isinstance(AppealDecision.UPHELD, str)


class TestInstitutionType:
    """InstitutionType enum tests."""

    def test_all_values_exist(self):
        """Verify all required institution type values exist."""
        assert hasattr(InstitutionType, "MINISTRY")
        assert hasattr(InstitutionType, "REGULATORY")
        assert hasattr(InstitutionType, "GENERAL_SERVICES")
        assert hasattr(InstitutionType, "INFRASTRUCTURE")
        assert hasattr(InstitutionType, "SECURITY")
        assert hasattr(InstitutionType, "GOVT_COMPANY")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert InstitutionType.MINISTRY.value == "MINISTRY"
        assert InstitutionType.REGULATORY.value == "REGULATORY"
        assert InstitutionType.GENERAL_SERVICES.value == "GENERAL_SERVICES"
        assert InstitutionType.INFRASTRUCTURE.value == "INFRASTRUCTURE"
        assert InstitutionType.SECURITY.value == "SECURITY"
        assert InstitutionType.GOVT_COMPANY.value == "GOVT_COMPANY"

    def test_is_str_enum(self):
        """Verify InstitutionType is a string enum."""
        assert isinstance(InstitutionType.MINISTRY, str)


class TestInstitutionalPerfStatus:
    """InstitutionalPerfStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required institutional perf status values exist."""
        assert hasattr(InstitutionalPerfStatus, "DRAFT")
        assert hasattr(InstitutionalPerfStatus, "UNDER_REVIEW")
        assert hasattr(InstitutionalPerfStatus, "APPRAISED")
        assert hasattr(InstitutionalPerfStatus, "RECONCILED")
        assert hasattr(InstitutionalPerfStatus, "COMPLETED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert InstitutionalPerfStatus.DRAFT.value == "DRAFT"
        assert InstitutionalPerfStatus.UNDER_REVIEW.value == "UNDER_REVIEW"
        assert InstitutionalPerfStatus.APPRAISED.value == "APPRAISED"
        assert InstitutionalPerfStatus.RECONCILED.value == "RECONCILED"
        assert InstitutionalPerfStatus.COMPLETED.value == "COMPLETED"

    def test_is_str_enum(self):
        """Verify InstitutionalPerfStatus is a string enum."""
        assert isinstance(InstitutionalPerfStatus.DRAFT, str)


class TestOutcomeActionType:
    """OutcomeActionType enum tests."""

    def test_all_values_exist(self):
        """Verify all required outcome action type values exist."""
        assert hasattr(OutcomeActionType, "REWARD")
        assert hasattr(OutcomeActionType, "PIP")
        assert hasattr(OutcomeActionType, "TRAINING")
        assert hasattr(OutcomeActionType, "TRANSFER")
        assert hasattr(OutcomeActionType, "PROMOTION")
        assert hasattr(OutcomeActionType, "DEMOTION")
        assert hasattr(OutcomeActionType, "REMOVAL")
        assert hasattr(OutcomeActionType, "COUNSELING")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert OutcomeActionType.REWARD.value == "REWARD"
        assert OutcomeActionType.PIP.value == "PIP"
        assert OutcomeActionType.TRAINING.value == "TRAINING"
        assert OutcomeActionType.TRANSFER.value == "TRANSFER"
        assert OutcomeActionType.PROMOTION.value == "PROMOTION"
        assert OutcomeActionType.DEMOTION.value == "DEMOTION"
        assert OutcomeActionType.REMOVAL.value == "REMOVAL"
        assert OutcomeActionType.COUNSELING.value == "COUNSELING"

    def test_is_str_enum(self):
        """Verify OutcomeActionType is a string enum."""
        assert isinstance(OutcomeActionType.REWARD, str)


class TestOutcomeActionStatus:
    """OutcomeActionStatus enum tests."""

    def test_all_values_exist(self):
        """Verify all required outcome action status values exist."""
        assert hasattr(OutcomeActionStatus, "PENDING")
        assert hasattr(OutcomeActionStatus, "COMPLETED")
        assert hasattr(OutcomeActionStatus, "CANCELLED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert OutcomeActionStatus.PENDING.value == "PENDING"
        assert OutcomeActionStatus.COMPLETED.value == "COMPLETED"
        assert OutcomeActionStatus.CANCELLED.value == "CANCELLED"

    def test_is_str_enum(self):
        """Verify OutcomeActionStatus is a string enum."""
        assert isinstance(OutcomeActionStatus.PENDING, str)


class TestConfirmationRecommendation:
    """ConfirmationRecommendation enum tests."""

    def test_all_values_exist(self):
        """Verify all required confirmation recommendation values exist."""
        assert hasattr(ConfirmationRecommendation, "CONFIRM")
        assert hasattr(ConfirmationRecommendation, "EXTEND")
        assert hasattr(ConfirmationRecommendation, "TERMINATE")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert ConfirmationRecommendation.CONFIRM.value == "CONFIRM"
        assert ConfirmationRecommendation.EXTEND.value == "EXTEND"
        assert ConfirmationRecommendation.TERMINATE.value == "TERMINATE"

    def test_is_str_enum(self):
        """Verify ConfirmationRecommendation is a string enum."""
        assert isinstance(ConfirmationRecommendation.CONFIRM, str)


class TestCommitteeDecision:
    """CommitteeDecision enum tests."""

    def test_all_values_exist(self):
        """Verify all required committee decision values exist."""
        assert hasattr(CommitteeDecision, "ENDORSED")
        assert hasattr(CommitteeDecision, "ADJUSTED")
        assert hasattr(CommitteeDecision, "DISPUTED")

    def test_string_values(self):
        """Verify enum values match their names."""
        assert CommitteeDecision.ENDORSED.value == "ENDORSED"
        assert CommitteeDecision.ADJUSTED.value == "ADJUSTED"
        assert CommitteeDecision.DISPUTED.value == "DISPUTED"

    def test_is_str_enum(self):
        """Verify CommitteeDecision is a string enum."""
        assert isinstance(CommitteeDecision.ENDORSED, str)


class TestEnumCount:
    """Verify total count of enums."""

    def test_all_enums_defined(self):
        """Verify all 14 enums are importable."""
        enums = [
            ContractStatus,
            ContractType,
            MonthlyReviewStatus,
            PIPStatus,
            PIPCauseCategory,
            PIPOutcome,
            AppealStatus,
            AppealDecision,
            InstitutionType,
            InstitutionalPerfStatus,
            OutcomeActionType,
            OutcomeActionStatus,
            ConfirmationRecommendation,
            CommitteeDecision,
        ]
        assert len(enums) == 14

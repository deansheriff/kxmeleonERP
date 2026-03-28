"""
OHCSF Appraisal Service.

Implements the OHCSF-specific multi-stage appraisal workflow:
  DRAFT → SELF_ASSESSMENT → PENDING_REVIEW → UNDER_REVIEW →
  PENDING_COUNTERSIGN → COUNTERSIGNED → PENDING_COMMITTEE → COMPLETED

Cascade-up rule: a supervisor cannot complete their appraisal until
all their direct reports have completed theirs in the same cycle.

Quarterly support: quarterly sub-cycles produce quarterly Appraisal
records that feed into the annual rating calculation.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.people.perf.appraisal import Appraisal, AppraisalKRAScore, AppraisalStatus
from app.models.people.perf.appraisal_cycle import AppraisalCycle
from app.models.people.perf.competency_assessment import CompetencyAssessment
from app.models.people.perf.pms_enums import CommitteeDecision
from app.services.people.perf.scoring_engine import OHCSFScoringEngine
from app.services.common import PaginatedResult, PaginationParams

if TYPE_CHECKING:
    from app.web.deps import WebAuthContext

logger = logging.getLogger(__name__)

TWO_DP = Decimal("0.01")

# ---------------------------------------------------------------------------
# Status transition map
# ---------------------------------------------------------------------------

OHCSF_STATUS_TRANSITIONS: dict[AppraisalStatus, set[AppraisalStatus]] = {
    AppraisalStatus.DRAFT: {AppraisalStatus.SELF_ASSESSMENT, AppraisalStatus.CANCELLED},
    AppraisalStatus.SELF_ASSESSMENT: {AppraisalStatus.PENDING_REVIEW, AppraisalStatus.DRAFT},
    AppraisalStatus.PENDING_REVIEW: {AppraisalStatus.UNDER_REVIEW},
    AppraisalStatus.UNDER_REVIEW: {
        AppraisalStatus.PENDING_COUNTERSIGN,
        AppraisalStatus.SELF_ASSESSMENT,
    },
    AppraisalStatus.PENDING_COUNTERSIGN: {AppraisalStatus.COUNTERSIGNED},
    AppraisalStatus.COUNTERSIGNED: {AppraisalStatus.PENDING_COMMITTEE},
    AppraisalStatus.PENDING_COMMITTEE: {AppraisalStatus.COMPLETED},
    AppraisalStatus.COMPLETED: set(),
    AppraisalStatus.CANCELLED: set(),
}

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class OHCSFAppraisalError(Exception):
    """Base error for OHCSF appraisal workflow."""


class OHCSFAppraisalNotFoundError(OHCSFAppraisalError):
    """Appraisal record not found."""

    def __init__(self, appraisal_id: UUID) -> None:
        self.appraisal_id = appraisal_id
        super().__init__(f"Appraisal {appraisal_id} not found")


class OHCSFAppraisalStatusError(OHCSFAppraisalError):
    """Invalid status transition."""

    def __init__(self, current: AppraisalStatus, target: AppraisalStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition appraisal from {current.value} to {target.value}"
        )


class CascadeUpViolation(OHCSFAppraisalError):
    """Supervisor cannot proceed until all direct reports are completed."""

    def __init__(self, incomplete_count: int) -> None:
        self.incomplete_count = incomplete_count
        super().__init__(
            f"Supervisor cannot be appraised until all subordinates complete "
            f"their appraisals ({incomplete_count} still incomplete)"
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class OHCSFAppraisalService:
    """Service for managing OHCSF appraisal workflow operations."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._scoring = OHCSFScoringEngine()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_404(self, org_id: UUID, appraisal_id: UUID) -> Appraisal:
        """Fetch appraisal by PK with org check, or raise OHCSFAppraisalNotFoundError."""
        appraisal = self.db.get(Appraisal, appraisal_id)
        if appraisal is None or appraisal.organization_id != org_id:
            raise OHCSFAppraisalNotFoundError(appraisal_id)
        return appraisal

    def _validate_transition(
        self, current: AppraisalStatus, target: AppraisalStatus
    ) -> None:
        """Raise OHCSFAppraisalStatusError if transition is not permitted."""
        allowed = OHCSF_STATUS_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise OHCSFAppraisalStatusError(current, target)

    def _check_cascade_up(
        self, org_id: UUID, cycle_id: UUID, employee_id: UUID
    ) -> None:
        """Raise CascadeUpViolation if any direct report has an incomplete appraisal.

        An appraisal is considered incomplete if its status is not COMPLETED or CANCELLED.
        """
        from app.models.people.hr.employee import Employee

        # Find direct reports of this employee
        direct_report_ids_stmt = select(Employee.employee_id).where(
            Employee.organization_id == org_id,
            Employee.reports_to_id == employee_id,
        )
        direct_report_ids = list(self.db.scalars(direct_report_ids_stmt).all())

        if not direct_report_ids:
            return  # No direct reports — no cascade-up constraint

        # Count their incomplete appraisals in this cycle
        terminal_statuses = {AppraisalStatus.COMPLETED, AppraisalStatus.CANCELLED}
        incomplete_count = self.db.scalar(
            select(func.count(Appraisal.appraisal_id)).where(
                Appraisal.organization_id == org_id,
                Appraisal.cycle_id == cycle_id,
                Appraisal.employee_id.in_(direct_report_ids),
                Appraisal.status.not_in(terminal_statuses),
            )
        ) or 0

        if incomplete_count > 0:
            raise CascadeUpViolation(incomplete_count)

    def _apply_kra_ratings(
        self,
        appraisal_id: UUID,
        org_id: UUID,
        kra_ratings: list[dict],
        *,
        rating_field: str,
        comments_field: str,
    ) -> None:
        """Upsert KRA score rows for self or manager ratings.

        Each entry in kra_ratings must have:
            kra_id (UUID | str), rating (int), comments (str, optional)
        """
        for entry in kra_ratings:
            kra_id = UUID(str(entry["kra_id"]))
            stmt = select(AppraisalKRAScore).where(
                AppraisalKRAScore.appraisal_id == appraisal_id,
                AppraisalKRAScore.kra_id == kra_id,
            )
            score_row = self.db.scalar(stmt)
            if score_row is None:
                score_row = AppraisalKRAScore(
                    organization_id=org_id,
                    appraisal_id=appraisal_id,
                    kra_id=kra_id,
                    weightage=Decimal(str(entry.get("weightage", "0"))),
                )
                self.db.add(score_row)

            setattr(score_row, rating_field, entry.get("rating"))
            if comments_field:
                setattr(score_row, comments_field, entry.get("comments"))

            # For manager ratings, also apply OHCSF threshold-based raw score
            if rating_field == "manager_rating":
                actual = entry.get("actual_achievement")
                if actual is not None:
                    score_row.actual_achievement = Decimal(str(actual))
                    thresholds: dict[str, Decimal] = {}
                    for band in ("outstanding", "excellent", "good", "fair", "poor"):
                        val = entry.get(f"{band}_threshold")
                        if val is not None:
                            thresholds[band] = Decimal(str(val))
                            setattr(score_row, f"{band}_threshold", thresholds[band])
                    if len(thresholds) == 5:
                        raw_pct = self._scoring.calculate_raw_score(
                            score_row.actual_achievement, thresholds
                        )
                        score_row.raw_score_percentage = raw_pct
                        weighted = self._scoring.calculate_weighted_score(
                            raw_pct, score_row.weightage / Decimal("100")
                        )
                        score_row.weighted_score = weighted
                        score_row.final_rating = entry.get("rating")

    def _compute_objective_score(self, appraisal_id: UUID) -> Decimal:
        """Sum weighted scores of all KRA score rows for this appraisal."""
        stmt = select(AppraisalKRAScore).where(
            AppraisalKRAScore.appraisal_id == appraisal_id,
        )
        rows = list(self.db.scalars(stmt).all())
        weighted_scores = [
            r.weighted_score for r in rows if r.weighted_score is not None
        ]
        return self._scoring.calculate_composite(weighted_scores)

    def _compute_competency_score(self, appraisal_id: UUID, org_id: UUID) -> Decimal:
        """Compute average final_rating across all competency assessments (scaled 0-100)."""
        stmt = select(CompetencyAssessment).where(
            CompetencyAssessment.appraisal_id == appraisal_id,
            CompetencyAssessment.organization_id == org_id,
        )
        rows = list(self.db.scalars(stmt).all())
        rated = [r.final_rating for r in rows if r.final_rating is not None]
        if not rated:
            return Decimal("0.00")
        # Scale: ratings are 1-5; map to 0-100 as (rating / 5) * 100
        avg = sum(rated) / len(rated)
        return (Decimal(str(avg)) / Decimal("5") * Decimal("100")).quantize(
            TWO_DP, rounding=ROUND_HALF_UP
        )

    def _apply_competency_ratings(
        self, appraisal_id: UUID, org_id: UUID, competency_ratings: list[dict]
    ) -> None:
        """Upsert manager final_rating on CompetencyAssessment rows."""
        for entry in competency_ratings:
            comp_id = UUID(str(entry["competency_id"]))
            stmt = select(CompetencyAssessment).where(
                CompetencyAssessment.appraisal_id == appraisal_id,
                CompetencyAssessment.competency_id == comp_id,
            )
            ca = self.db.scalar(stmt)
            if ca is None:
                ca = CompetencyAssessment(
                    organization_id=org_id,
                    appraisal_id=appraisal_id,
                    competency_id=comp_id,
                )
                self.db.add(ca)
            ca.manager_rating = entry.get("manager_rating")
            ca.final_rating = entry.get("final_rating", entry.get("manager_rating"))

    # ------------------------------------------------------------------
    # Workflow actions
    # ------------------------------------------------------------------

    def submit_self_assessment_ohcsf(
        self,
        org_id: UUID,
        appraisal_id: UUID,
        *,
        self_overall_rating: int,
        self_summary: str,
        achievements: Optional[str] = None,
        challenges: Optional[str] = None,
        development_needs: Optional[str] = None,
        kra_ratings: Optional[list[dict]] = None,
    ) -> Appraisal:
        """Employee submits self-assessment; transitions to PENDING_REVIEW.

        Valid starting statuses: DRAFT or SELF_ASSESSMENT.
        Enforces cascade-up rule: all direct-report appraisals must be complete.
        """
        appraisal = self._get_or_404(org_id, appraisal_id)

        # Both DRAFT and SELF_ASSESSMENT can move to PENDING_REVIEW
        if appraisal.status not in (
            AppraisalStatus.DRAFT,
            AppraisalStatus.SELF_ASSESSMENT,
        ):
            raise OHCSFAppraisalStatusError(appraisal.status, AppraisalStatus.PENDING_REVIEW)

        self._check_cascade_up(org_id, appraisal.cycle_id, appraisal.employee_id)

        appraisal.self_assessment_date = date.today()
        appraisal.self_overall_rating = self_overall_rating
        appraisal.self_summary = self_summary
        if achievements is not None:
            appraisal.achievements = achievements
        if challenges is not None:
            appraisal.challenges = challenges
        if development_needs is not None:
            appraisal.development_needs = development_needs

        if kra_ratings:
            self._apply_kra_ratings(
                appraisal_id,
                org_id,
                kra_ratings,
                rating_field="self_rating",
                comments_field="self_comments",
            )

        appraisal.status = AppraisalStatus.PENDING_REVIEW
        self.db.flush()
        logger.info(
            "OHCSF self-assessment submitted: appraisal=%s employee=%s",
            appraisal_id,
            appraisal.employee_id,
        )
        return appraisal

    def submit_manager_review_ohcsf(
        self,
        org_id: UUID,
        appraisal_id: UUID,
        *,
        manager_overall_rating: int,
        manager_summary: str,
        manager_recommendations: Optional[str] = None,
        kra_ratings: Optional[list[dict]] = None,
        competency_ratings: Optional[list[dict]] = None,
        process_rating: Optional[int] = None,
    ) -> Appraisal:
        """Manager submits review; calculates composite scores; transitions to PENDING_COUNTERSIGN."""
        appraisal = self._get_or_404(org_id, appraisal_id)
        self._validate_transition(appraisal.status, AppraisalStatus.PENDING_COUNTERSIGN)

        appraisal.manager_review_date = date.today()
        appraisal.manager_overall_rating = manager_overall_rating
        appraisal.manager_summary = manager_summary
        if manager_recommendations is not None:
            appraisal.manager_recommendations = manager_recommendations

        if kra_ratings:
            self._apply_kra_ratings(
                appraisal_id,
                org_id,
                kra_ratings,
                rating_field="manager_rating",
                comments_field="manager_comments",
            )

        if competency_ratings:
            self._apply_competency_ratings(appraisal_id, org_id, competency_ratings)

        # Process scoring (10% bucket) — scale 1-5 rating to 0-100
        if process_rating is not None:
            appraisal.process_manager_rating = process_rating
            appraisal.process_final_rating = process_rating

        # Flush so KRA/competency rows are visible for scoring
        self.db.flush()

        # Calculate composite scores
        objective_score = self._compute_objective_score(appraisal_id)
        competency_score = self._compute_competency_score(appraisal_id, org_id)
        process_score = (
            (Decimal(str(appraisal.process_final_rating)) / Decimal("5") * Decimal("100"))
            .quantize(TWO_DP, rounding=ROUND_HALF_UP)
            if appraisal.process_final_rating
            else Decimal("0.00")
        )

        appraisal.objective_weighted_score = objective_score
        appraisal.competency_weighted_score = competency_score
        appraisal.process_weighted_score = process_score

        final = self._scoring.calculate_appraisal_final(
            objective_score, competency_score, process_score
        )
        appraisal.final_score = final
        rating_int, label = self._scoring.score_to_rating(final)
        appraisal.final_rating = rating_int
        appraisal.rating_label = label

        appraisal.status = AppraisalStatus.PENDING_COUNTERSIGN
        self.db.flush()
        logger.info(
            "OHCSF manager review submitted: appraisal=%s final_score=%s rating=%s",
            appraisal_id,
            final,
            label,
        )
        return appraisal

    def submit_countersign(
        self,
        org_id: UUID,
        appraisal_id: UUID,
        *,
        counter_signer_id: UUID,
        comments: Optional[str] = None,
    ) -> Appraisal:
        """Countersigner endorses the appraisal; transitions to COUNTERSIGNED."""
        appraisal = self._get_or_404(org_id, appraisal_id)
        self._validate_transition(appraisal.status, AppraisalStatus.COUNTERSIGNED)

        appraisal.counter_signer_id = counter_signer_id
        appraisal.counter_signer_date = date.today()
        if comments is not None:
            appraisal.counter_signer_comments = comments

        appraisal.status = AppraisalStatus.COUNTERSIGNED
        self.db.flush()
        logger.info(
            "OHCSF countersigned: appraisal=%s counter_signer=%s",
            appraisal_id,
            counter_signer_id,
        )
        return appraisal

    def submit_committee_review(
        self,
        org_id: UUID,
        appraisal_id: UUID,
        *,
        decision: CommitteeDecision,
        notes: Optional[str] = None,
        adjusted_rating: Optional[int] = None,
    ) -> Appraisal:
        """Committee reviews countersigned appraisal; transitions to COMPLETED."""
        appraisal = self._get_or_404(org_id, appraisal_id)

        # Accept from COUNTERSIGNED (auto-advance) or PENDING_COMMITTEE
        if appraisal.status == AppraisalStatus.COUNTERSIGNED:
            # Validate COUNTERSIGNED → PENDING_COMMITTEE first
            self._validate_transition(appraisal.status, AppraisalStatus.PENDING_COMMITTEE)
        elif appraisal.status == AppraisalStatus.PENDING_COMMITTEE:
            self._validate_transition(appraisal.status, AppraisalStatus.COMPLETED)
        else:
            # Any other status is invalid — raise via the PENDING_COMMITTEE path
            # so the error reflects the actual current status
            self._validate_transition(appraisal.status, AppraisalStatus.COMPLETED)

        appraisal.committee_review_date = date.today()
        appraisal.committee_decision = decision.value
        if notes is not None:
            appraisal.committee_notes = notes

        if decision == CommitteeDecision.ADJUSTED and adjusted_rating is not None:
            appraisal.final_rating = adjusted_rating
            _, label = self._scoring.score_to_rating(
                Decimal(str(adjusted_rating)) / Decimal("5") * Decimal("100")
            )
            appraisal.rating_label = label

        appraisal.status = AppraisalStatus.COMPLETED
        appraisal.completed_on = date.today()
        self.db.flush()
        logger.info(
            "OHCSF committee review completed: appraisal=%s decision=%s",
            appraisal_id,
            decision.value,
        )
        return appraisal

    # ------------------------------------------------------------------
    # Quarterly appraisal creation
    # ------------------------------------------------------------------

    def create_quarterly_appraisals(
        self, org_id: UUID, cycle_id: UUID, quarter: int
    ) -> list[Appraisal]:
        """Create quarterly Appraisal records for all employees with active contracts.

        Finds the quarterly sub-cycle matching the given parent cycle and quarter,
        then creates one Appraisal per employee with an ACTIVE PerformanceContract
        for that cycle.

        Returns:
            List of newly created Appraisal records.
        """
        from app.models.people.perf.performance_contract import PerformanceContract
        from app.models.people.perf.pms_enums import ContractStatus

        # Find the quarterly sub-cycle
        sub_cycle = self.db.scalar(
            select(AppraisalCycle).where(
                AppraisalCycle.organization_id == org_id,
                AppraisalCycle.parent_cycle_id == cycle_id,
                AppraisalCycle.quarter == quarter,
            )
        )
        if sub_cycle is None:
            logger.warning(
                "No quarterly sub-cycle found for cycle=%s quarter=%s", cycle_id, quarter
            )
            return []

        # Find employees with ACTIVE contracts for the parent cycle
        active_contracts = list(
            self.db.scalars(
                select(PerformanceContract).where(
                    PerformanceContract.organization_id == org_id,
                    PerformanceContract.cycle_id == cycle_id,
                    PerformanceContract.status == ContractStatus.ACTIVE,
                )
            ).all()
        )

        created: list[Appraisal] = []
        for contract in active_contracts:
            # Check if appraisal already exists for this sub-cycle
            existing = self.db.scalar(
                select(Appraisal).where(
                    Appraisal.organization_id == org_id,
                    Appraisal.cycle_id == sub_cycle.cycle_id,
                    Appraisal.employee_id == contract.employee_id,
                )
            )
            if existing is not None:
                continue  # Skip duplicates

            appraisal = Appraisal(
                organization_id=org_id,
                employee_id=contract.employee_id,
                manager_id=contract.supervisor_id,
                cycle_id=sub_cycle.cycle_id,
                status=AppraisalStatus.DRAFT,
                is_quarterly=True,
            )
            self.db.add(appraisal)
            created.append(appraisal)

        self.db.flush()
        logger.info(
            "Created %d quarterly appraisals: cycle=%s quarter=%s",
            len(created),
            cycle_id,
            quarter,
        )
        return created

    # ------------------------------------------------------------------
    # Annual rating calculation
    # ------------------------------------------------------------------

    def calculate_annual_rating(
        self, org_id: UUID, cycle_id: UUID, employee_id: UUID
    ) -> dict:
        """Average quarterly ratings to produce an annual score.

        Fetches all quarterly Appraisal records for the employee in sub-cycles
        of the given annual cycle, averages the quarterly_rating values, and
        returns a structured result dict.

        Returns:
            {
                "employee_id": UUID,
                "quarterly_scores": [{"quarter": int, "score": Decimal}, ...],
                "annual_score": Decimal,
                "rating": int,
                "label": str,
            }
        """
        # Find quarterly sub-cycles under this annual cycle
        sub_cycle_ids_stmt = select(AppraisalCycle.cycle_id).where(
            AppraisalCycle.organization_id == org_id,
            AppraisalCycle.parent_cycle_id == cycle_id,
        )
        sub_cycle_id_list = list(self.db.scalars(sub_cycle_ids_stmt).all())

        if not sub_cycle_id_list:
            return {
                "employee_id": employee_id,
                "quarterly_scores": [],
                "annual_score": Decimal("0.00"),
                "rating": 1,
                "label": "Poor",
            }

        appraisals = list(
            self.db.scalars(
                select(Appraisal).where(
                    Appraisal.organization_id == org_id,
                    Appraisal.cycle_id.in_(sub_cycle_id_list),
                    Appraisal.employee_id == employee_id,
                    Appraisal.is_quarterly.is_(True),
                    Appraisal.status == AppraisalStatus.COMPLETED,
                )
            ).all()
        )

        quarterly_scores: list[dict] = []
        for ap in appraisals:
            score = ap.quarterly_rating if ap.quarterly_rating is not None else ap.final_score
            if score is not None:
                quarterly_scores.append(
                    {
                        "appraisal_id": ap.appraisal_id,
                        "cycle_id": ap.cycle_id,
                        "score": score,
                    }
                )

        if not quarterly_scores:
            return {
                "employee_id": employee_id,
                "quarterly_scores": [],
                "annual_score": Decimal("0.00"),
                "rating": 1,
                "label": "Poor",
            }

        total = sum(entry["score"] for entry in quarterly_scores)
        annual_score = (total / Decimal(str(len(quarterly_scores)))).quantize(
            TWO_DP, rounding=ROUND_HALF_UP
        )
        rating_int, label = self._scoring.score_to_rating(annual_score)

        return {
            "employee_id": employee_id,
            "quarterly_scores": quarterly_scores,
            "annual_score": annual_score,
            "rating": rating_int,
            "label": label,
        }

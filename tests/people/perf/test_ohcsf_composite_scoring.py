"""
Integration tests for the OHCSF 70/20/10 composite scoring pipeline.

Tests the full scoring computation with realistic data matching the OHCSF
guidelines worked examples. Exercises _compute_objective_score,
_compute_competency_score, and the calculate_appraisal_final formula.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.people.perf.ohcsf_appraisal_service import OHCSFAppraisalService
from app.services.people.perf.scoring_engine import OHCSFScoringEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_kra_score_row(
    weighted_score: float | None,
    raw_score_percentage: float | None = None,
    weightage: float = 0.0,
    actual_achievement: float | None = None,
    outstanding_threshold: float | None = None,
    excellent_threshold: float | None = None,
    good_threshold: float | None = None,
    fair_threshold: float | None = None,
    poor_threshold: float | None = None,
) -> SimpleNamespace:
    """Create a mock AppraisalKRAScore row with threshold fields."""
    return SimpleNamespace(
        score_id=uuid4(),
        kra_id=uuid4(),
        weighted_score=Decimal(str(weighted_score))
        if weighted_score is not None
        else None,
        raw_score_percentage=(
            Decimal(str(raw_score_percentage))
            if raw_score_percentage is not None
            else None
        ),
        weightage=Decimal(str(weightage)),
        actual_achievement=(
            Decimal(str(actual_achievement)) if actual_achievement is not None else None
        ),
        outstanding_threshold=(
            Decimal(str(outstanding_threshold))
            if outstanding_threshold is not None
            else None
        ),
        excellent_threshold=(
            Decimal(str(excellent_threshold))
            if excellent_threshold is not None
            else None
        ),
        good_threshold=(
            Decimal(str(good_threshold)) if good_threshold is not None else None
        ),
        fair_threshold=(
            Decimal(str(fair_threshold)) if fair_threshold is not None else None
        ),
        poor_threshold=(
            Decimal(str(poor_threshold)) if poor_threshold is not None else None
        ),
    )


def make_competency_row(final_rating: int | None) -> SimpleNamespace:
    """Create a mock CompetencyAssessment row."""
    return SimpleNamespace(
        assessment_id=uuid4(),
        competency_id=uuid4(),
        final_rating=final_rating,
        manager_rating=final_rating,
    )


def make_service_with_kra_rows(rows: list) -> OHCSFAppraisalService:
    """Return OHCSFAppraisalService with db.scalars mocked to yield given KRA rows."""
    db = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = rows
    db.scalars.return_value = mock_scalars
    return OHCSFAppraisalService(db)


def make_service_with_competency_rows(rows: list) -> OHCSFAppraisalService:
    """Return OHCSFAppraisalService with db.scalars mocked to yield given competency rows."""
    db = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = rows
    db.scalars.return_value = mock_scalars
    return OHCSFAppraisalService(db)


# ---------------------------------------------------------------------------
# Direct engine tests for raw/weighted/composite (engine already tested in
# test_scoring_engine.py — here we focus on the worked-example numbers from
# the OHCSF guidelines).
# ---------------------------------------------------------------------------


class TestOHCSFGuidelinesWorkedExample:
    """Reproduce the numeric worked example from the OHCSF PMS Guidelines."""

    # KRA 1: weight=50%, thresholds 85/80/70/60/50, actual=65
    #   → falls in [fair=60, good=70): ratio=(65-60)/(70-60)=0.5
    #   → score = 70 + 0.5*(80-70) = 75%
    #   → weighted = 75 * 0.50 = 37.50
    #
    # KRA 2: weight=30%, thresholds 20/15/10/5/2, actual=10
    #   → falls at good threshold exactly (actual==good=10)
    #   → score = 80 + 0*(90-80) = 80%
    #   → weighted = 80 * 0.30 = 24.00
    #
    # KRA 3: weight=20%, thresholds 50/40/30/20/10, actual=60
    #   → actual >= outstanding (60 >= 50) → score = 100%
    #   → weighted = 100 * 0.20 = 20.00
    #
    # Composite = 37.50 + 24.00 + 20.00 = 81.50

    _engine = OHCSFScoringEngine()

    _kra1_thresholds = {
        "outstanding": Decimal("85"),
        "excellent": Decimal("80"),
        "good": Decimal("70"),
        "fair": Decimal("60"),
        "poor": Decimal("50"),
    }
    _kra2_thresholds = {
        "outstanding": Decimal("20"),
        "excellent": Decimal("15"),
        "good": Decimal("10"),
        "fair": Decimal("5"),
        "poor": Decimal("2"),
    }
    _kra3_thresholds = {
        "outstanding": Decimal("50"),
        "excellent": Decimal("40"),
        "good": Decimal("30"),
        "fair": Decimal("20"),
        "poor": Decimal("10"),
    }

    def test_kra1_raw_score(self) -> None:
        """KRA 1: actual=65 in [fair,good) band → raw score 75%."""
        raw = self._engine.calculate_raw_score(Decimal("65"), self._kra1_thresholds)
        assert raw == Decimal("75.00")

    def test_kra2_raw_score(self) -> None:
        """KRA 2: actual=10 at good threshold exactly → raw score 80%."""
        raw = self._engine.calculate_raw_score(Decimal("10"), self._kra2_thresholds)
        assert raw == Decimal("80.00")

    def test_kra3_raw_score_outstanding(self) -> None:
        """KRA 3: actual=60 >= outstanding threshold (50) → raw score 100%."""
        raw = self._engine.calculate_raw_score(Decimal("60"), self._kra3_thresholds)
        assert raw == Decimal("100.00")

    def test_kra1_weighted_score(self) -> None:
        """KRA 1: raw=75% × weight=0.50 → weighted score 37.50."""
        weighted = self._engine.calculate_weighted_score(Decimal("75"), Decimal("0.50"))
        assert weighted == Decimal("37.50")

    def test_kra2_weighted_score(self) -> None:
        """KRA 2: raw=80% × weight=0.30 → weighted score 24.00."""
        weighted = self._engine.calculate_weighted_score(Decimal("80"), Decimal("0.30"))
        assert weighted == Decimal("24.00")

    def test_kra3_weighted_score(self) -> None:
        """KRA 3: raw=100% × weight=0.20 → weighted score 20.00."""
        weighted = self._engine.calculate_weighted_score(
            Decimal("100"), Decimal("0.20")
        )
        assert weighted == Decimal("20.00")

    def test_objective_composite_equals_81_50(self) -> None:
        """Composite of three KRAs = 37.50 + 24.00 + 20.00 = 81.50."""
        composite = self._engine.calculate_composite(
            [Decimal("37.50"), Decimal("24.00"), Decimal("20.00")]
        )
        assert composite == Decimal("81.50")


# ---------------------------------------------------------------------------
# _compute_objective_score via OHCSFAppraisalService
# ---------------------------------------------------------------------------


class TestComputeObjectiveScore:
    """Test _compute_objective_score by mocking DB KRA score rows."""

    def test_objective_score_with_three_kras(self) -> None:
        """_compute_objective_score sums pre-computed weighted_score values."""
        rows = [
            make_kra_score_row(weighted_score=37.50),
            make_kra_score_row(weighted_score=24.00),
            make_kra_score_row(weighted_score=20.00),
        ]
        svc = make_service_with_kra_rows(rows)
        appraisal_id = uuid4()
        org_id = uuid4()

        result = svc._compute_objective_score(appraisal_id, org_id)

        assert result == Decimal("81.50")

    def test_objective_score_ignores_null_weighted_scores(self) -> None:
        """KRA rows without weighted_score are excluded from the sum."""
        rows = [
            make_kra_score_row(weighted_score=50.00),
            make_kra_score_row(weighted_score=None),  # not yet scored
            make_kra_score_row(weighted_score=20.00),
        ]
        svc = make_service_with_kra_rows(rows)

        result = svc._compute_objective_score(uuid4(), uuid4())

        assert result == Decimal("70.00")

    def test_objective_score_returns_zero_when_no_rows(self) -> None:
        """No KRA rows → objective score is 0.00."""
        svc = make_service_with_kra_rows([])

        result = svc._compute_objective_score(uuid4(), uuid4())

        assert result == Decimal("0.00")

    def test_objective_score_with_single_full_weight_kra(self) -> None:
        """Single KRA with weight=1.0 → composite equals its weighted score."""
        rows = [make_kra_score_row(weighted_score=85.00)]
        svc = make_service_with_kra_rows(rows)

        result = svc._compute_objective_score(uuid4(), uuid4())

        assert result == Decimal("85.00")


# ---------------------------------------------------------------------------
# _compute_competency_score via OHCSFAppraisalService
# ---------------------------------------------------------------------------


class TestComputeCompetencyScore:
    """Test _compute_competency_score with realistic rating data."""

    def test_competency_score_with_three_ratings(self) -> None:
        """Three ratings [4, 3, 3]: avg=3.33, scaled=(3.33/5)*100=66.67."""
        rows = [
            make_competency_row(final_rating=4),
            make_competency_row(final_rating=3),
            make_competency_row(final_rating=3),
        ]
        svc = make_service_with_competency_rows(rows)

        result = svc._compute_competency_score(uuid4(), uuid4())

        # avg = 10/3 = 3.3333... → (3.3333/5)*100 = 66.67 (ROUND_HALF_UP)
        assert result == Decimal("66.67")

    def test_competency_score_with_all_excellent(self) -> None:
        """All ratings 4/5 (Excellent): avg=4, scaled=(4/5)*100=80.00."""
        rows = [
            make_competency_row(final_rating=4),
            make_competency_row(final_rating=4),
            make_competency_row(final_rating=4),
        ]
        svc = make_service_with_competency_rows(rows)

        result = svc._compute_competency_score(uuid4(), uuid4())

        assert result == Decimal("80.00")

    def test_competency_score_with_all_outstanding(self) -> None:
        """All ratings 5 (Outstanding): avg=5, scaled=(5/5)*100=100.00."""
        rows = [
            make_competency_row(final_rating=5),
            make_competency_row(final_rating=5),
        ]
        svc = make_service_with_competency_rows(rows)

        result = svc._compute_competency_score(uuid4(), uuid4())

        assert result == Decimal("100.00")

    def test_competency_score_returns_zero_when_no_rows(self) -> None:
        """No competency assessments → score is 0.00."""
        svc = make_service_with_competency_rows([])

        result = svc._compute_competency_score(uuid4(), uuid4())

        assert result == Decimal("0.00")

    def test_competency_score_ignores_null_ratings(self) -> None:
        """Rows without final_rating are excluded from the average."""
        rows = [
            make_competency_row(final_rating=4),
            make_competency_row(final_rating=None),  # not yet rated
            make_competency_row(final_rating=None),
        ]
        svc = make_service_with_competency_rows(rows)

        result = svc._compute_competency_score(uuid4(), uuid4())

        # Only 1 rated row: avg=4 → (4/5)*100 = 80.00
        assert result == Decimal("80.00")


# ---------------------------------------------------------------------------
# Full 70/20/10 formula via OHCSFScoringEngine
# ---------------------------------------------------------------------------


class TestFullCompositeFormula:
    """Test calculate_appraisal_final with the complete 70/20/10 formula."""

    _engine = OHCSFScoringEngine()

    def test_full_70_20_10_calculation(self) -> None:
        """objectives(58.30) * 0.70 + competency(16.67) * 0.20 + process(8.00) * 0.10
        Wait — use simpler round numbers:
        objectives=83.33, competency=80.00, process=80.00
        = 83.33*0.70 + 80.00*0.20 + 80.00*0.10
        = 58.33 + 16.00 + 8.00 = 82.33
        """
        result = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("83.33"),
            competency_score=Decimal("80.00"),
            process_score=Decimal("80.00"),
        )
        assert result == Decimal("82.33")

    def test_full_formula_worked_example(self) -> None:
        """objectives=81.50, competency=66.67, process=80.00
        = 81.50*0.70 + 66.67*0.20 + 80.00*0.10
        = 57.05 + 13.33 + 8.00 = 78.38
        """
        result = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("81.50"),
            competency_score=Decimal("66.67"),
            process_score=Decimal("80.00"),
        )
        assert result == Decimal("78.38")

    def test_all_outstanding_produces_100(self) -> None:
        """100% in all three components → final score 100.00."""
        result = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("100.00"),
            competency_score=Decimal("100.00"),
            process_score=Decimal("100.00"),
        )
        assert result == Decimal("100.00")

    def test_all_zero_produces_zero(self) -> None:
        """0% in all components → final score 0.00."""
        result = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("0.00"),
            competency_score=Decimal("0.00"),
            process_score=Decimal("0.00"),
        )
        assert result == Decimal("0.00")


# ---------------------------------------------------------------------------
# Process score scaling
# ---------------------------------------------------------------------------


class TestProcessScoreCalculation:
    """Test that process rating (1-5) maps to the correct 0-100 score."""

    _engine = OHCSFScoringEngine()

    def test_process_rating_4_gives_80_percent(self) -> None:
        """Process rating 4 (Good/Excellent) → (4/5)*100 = 80.00 → 10% bucket = 8.00."""
        process_pct = Decimal("4") / Decimal("5") * Decimal("100")
        process_contribution = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("0"),
            process_score=process_pct,
        )
        # Only process contributes: 80 * 0.10 = 8.00
        assert process_contribution == Decimal("8.00")

    def test_process_rating_5_gives_100_percent(self) -> None:
        """Process rating 5 (Outstanding) → 100% → 10% bucket = 10.00."""
        process_pct = Decimal("100")
        contribution = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("0"),
            process_score=process_pct,
        )
        assert contribution == Decimal("10.00")

    def test_process_rating_1_gives_20_percent(self) -> None:
        """Process rating 1 (Poor) → (1/5)*100 = 20% → 10% bucket = 2.00."""
        process_pct = Decimal("20")
        contribution = self._engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("0"),
            process_score=process_pct,
        )
        assert contribution == Decimal("2.00")


# ---------------------------------------------------------------------------
# score_to_rating mapping
# ---------------------------------------------------------------------------


class TestScoreToRatingMapping:
    """Test the rating band mapping for key boundary values."""

    _engine = OHCSFScoringEngine()

    def test_82_33_maps_to_excellent(self) -> None:
        """Score 82.33% falls in Excellent band (≥80, <90) → rating 4."""
        rating, label = self._engine.score_to_rating(Decimal("82.33"))
        assert rating == 4
        assert label == "Excellent"

    def test_78_38_maps_to_good(self) -> None:
        """Score 78.38% falls in Good band (≥70, <80) → rating 3."""
        rating, label = self._engine.score_to_rating(Decimal("78.38"))
        assert rating == 3
        assert label == "Good"

    def test_90_maps_to_outstanding(self) -> None:
        """Score exactly 90% → Outstanding (rating 5)."""
        rating, label = self._engine.score_to_rating(Decimal("90.00"))
        assert rating == 5
        assert label == "Outstanding"

    def test_89_99_maps_to_excellent(self) -> None:
        """Score 89.99% → just below Outstanding → Excellent (rating 4)."""
        rating, label = self._engine.score_to_rating(Decimal("89.99"))
        assert rating == 4
        assert label == "Excellent"

    def test_80_maps_to_excellent(self) -> None:
        """Score exactly 80% → Excellent (rating 4)."""
        rating, label = self._engine.score_to_rating(Decimal("80.00"))
        assert rating == 4
        assert label == "Excellent"

    def test_70_maps_to_good(self) -> None:
        """Score exactly 70% → Good (rating 3)."""
        rating, label = self._engine.score_to_rating(Decimal("70.00"))
        assert rating == 3
        assert label == "Good"

    def test_60_maps_to_fair(self) -> None:
        """Score exactly 60% → Fair (rating 2)."""
        rating, label = self._engine.score_to_rating(Decimal("60.00"))
        assert rating == 2
        assert label == "Fair"

    def test_59_99_maps_to_poor(self) -> None:
        """Score 59.99% → just below Fair → Poor (rating 1)."""
        rating, label = self._engine.score_to_rating(Decimal("59.99"))
        assert rating == 1
        assert label == "Poor"

    def test_zero_maps_to_poor(self) -> None:
        """Score 0% → Poor (rating 1)."""
        rating, label = self._engine.score_to_rating(Decimal("0.00"))
        assert rating == 1
        assert label == "Poor"

    def test_100_maps_to_outstanding(self) -> None:
        """Score 100% → Outstanding (rating 5)."""
        rating, label = self._engine.score_to_rating(Decimal("100.00"))
        assert rating == 5
        assert label == "Outstanding"

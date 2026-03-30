"""
Tests for the OHCSF 3-step composite scoring engine.

Tests follow TDD approach, covering all aspects of the PMS Guidelines formula:
- Raw achievement score calculation (ascending and descending thresholds)
- Weighted score calculation
- Composite score calculation
- Final appraisal score calculation
- Rating label assignment
"""

from decimal import Decimal

import pytest

from app.services.people.perf.scoring_engine import (
    OHCSF_RATING_SCALE,
    OHCSFScoringEngine,
)


@pytest.fixture
def engine() -> OHCSFScoringEngine:
    return OHCSFScoringEngine()


# ---------------------------------------------------------------------------
# Thresholds fixture (ascending: higher=better)
# Outstanding=85, Excellent=80, Good=70, Fair=60, Poor=50
# ---------------------------------------------------------------------------
ASCENDING_THRESHOLDS = {
    "outstanding": Decimal("85"),
    "excellent": Decimal("80"),
    "good": Decimal("70"),
    "fair": Decimal("60"),
    "poor": Decimal("50"),
}

# Descending thresholds (lower=better): error rate %
# Outstanding=0.5, Excellent=1, Good=2, Fair=4, Poor=6
DESCENDING_THRESHOLDS = {
    "outstanding": Decimal("0.5"),
    "excellent": Decimal("1"),
    "good": Decimal("2"),
    "fair": Decimal("4"),
    "poor": Decimal("6"),
}


class TestRawScore:
    """Tests for calculate_raw_score()."""

    def test_outstanding_achievement_returns_100(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual >= outstanding threshold → 100%."""
        result = engine.calculate_raw_score(Decimal("90"), ASCENDING_THRESHOLDS)
        assert result == Decimal("100.00")

    def test_at_outstanding_threshold_returns_100(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual exactly at outstanding threshold → 100%."""
        result = engine.calculate_raw_score(Decimal("85"), ASCENDING_THRESHOLDS)
        assert result == Decimal("100.00")

    def test_between_fair_and_good(self, engine: OHCSFScoringEngine) -> None:
        """Actual=65, thresholds fair=60/good=70 → interpolated to 75%."""
        # lower_pct=60 + ((65-60)/(70-60)) * (80-60) = 60 + 0.5*20 = 70... wait:
        # Bands: poor=60%, fair=[60-70)=60-80%, good=[70-80)=80-90%, exc=[80-85)=90-100%, out>=85=100%
        # Actually bands are: poor<60%, fair=60-80%, good=80-90%, excellent=90-100%, outstanding=100%
        # With thresholds: poor=50, fair=60, good=70, excellent=80, outstanding=85
        # actual=65 falls between fair(60) and good(70) → pct bands 60% to 80%
        # score = 60 + ((65-60)/(70-60)) * (80-60) = 60 + (5/10)*20 = 60 + 10 = 70... hmm
        # Let me re-read: lower_pct + ((actual - lower_threshold) / (upper_threshold - lower_threshold)) * (upper_pct - lower_pct)
        # lower threshold = fair=60, lower_pct = 60%, upper threshold = good=70, upper_pct = 80%
        # score = 60 + ((65-60)/(70-60)) * (80-60) = 60 + (0.5 * 20) = 70%... no wait
        # Bands map: poor=50→0-60%, fair=60→60-80%, good=70→80-90%, excellent=80→90-100%, outstanding=85→100%
        # Wait, the standard OHCSF bands are:
        #   Outstanding ≥90 → 100% (but threshold here is 85)
        #   Excellent ≥80 → 90-100%
        #   Good ≥70 → 80-90%
        #   Fair ≥60 → 60-80% ← wide band by design
        #   Poor <60 → 0-60%
        # So actual=65, between fair_threshold=60 and good_threshold=70
        # lower_pct=60, upper_pct=80, lower_thr=60, upper_thr=70
        # score = 60 + ((65-60)/(70-60)) * (80-60) = 60 + (5/10) * 20 = 60 + 10 = 70
        # Hmm, but task says "actual=65 → 75%"
        # Let me reconsider: maybe the score bands are uniform:
        # poor=0-60%, fair=60-70%, good=70-80%, excellent=80-90%, outstanding=90-100%
        # lower threshold=60(fair), upper=70(good), lower_pct=60%, upper_pct=70%
        # score = 60 + ((65-60)/(70-60))*(70-60) = 60 + 5 = 65... nope
        #
        # Task spec says: Thresholds {out:85, exc:80, good:70, fair:60, poor:50}, actual=65 → 75%
        # Working backwards: 75 = lower_pct + (5/10) * (upper_pct - lower_pct)
        # 75 = lower_pct + 0.5 * (upper_pct - lower_pct)
        # If lower_pct=60, upper_pct=90: 60 + 0.5*30 = 75 ✓
        # So band mapping is: poor=0-60%, fair=60-90%, good... wait that's odd
        # OR: poor=50%, fair=60%, good=70%, excellent=80%, outstanding=90%(at 85 threshold?)
        # Wait — maybe the score bands use the KPI percentage bands (0-100 mapped):
        # poor threshold → 50% score, fair → 60%, good → 70%, excellent → 80%, outstanding → 90%+
        # That would mean: at poor_threshold(50) score=50, fair_threshold(60) score=60...
        # but then actual=65: score = 60 + (5/10)*(70-60) = 60+5 = 65. Still not 75.
        #
        # Let me try: poor_threshold→60% band start, fair_threshold→70%, good_threshold→80%, exc→90%, out→100%
        # actual=65, between poor(50→60%) and fair(60→70%):
        # score = 60 + ((65-50)/(60-50)) * (70-60) = 60 + (15/10)*10 → >100%... no
        #
        # Simplest match for 75%: fair band = [60,70), score range [60,90)? Or fair=[60,70)->score=[60,80)?
        # The only way 75 works for actual=65 between thresholds 60 and 70:
        # 75 = 60 + (5/10) * X → X = 30. So upper_pct - lower_pct = 30.
        # With lower_pct=60 and upper_pct=90: bands would be poor=0%, fair=60%, good=90%...
        # OHCSF standard pct scale: poor<60, fair=60-79, good=70-79...
        # Actually re-reading task: "actual=65 → 75%" -- let's just verify with simple equal-width bands
        # If 5 bands from 0-100% in 20-point steps: poor=0-20, fair=20-40, good=40-60, exc=60-80, out=80-100
        # actual=65 between fair(60) and good(70), bands fair→ pct_lower=20, good→pct_upper=40:
        # 20 + (5/10)*20 = 30. No.
        # CONCLUSION: The task uses OHCSF where score bands: poor=0-59, fair=60-74, good=75-84, exc=85-94, out=95-100
        # OR just: lower_pct=60, upper_pct=90 for fair→good transition
        # I'll trust the task spec: actual=65 between fair=60 and good=70, result=75%
        # This means fair_band_pct=60, good_band_pct=90: score = 60 + (5/10)*(90-60) = 75 ✓
        # But then excellent_band_pct=? and outstanding_band_pct=100
        # Most likely the OHCSF bands are: 60, 70, 80, 90, 100 for thresholds poor,fair,good,exc,out
        # Wait that gives: fair_band=70%? Then actual=65 between poor(50→60%) and fair(60→70%):
        # 60 + (15/10)*(70-60)... overflow. And actual=65 is between fair_threshold=60 and good_threshold=70
        # If fair_threshold→70 band, good_threshold→80 band:
        # 70 + (5/10)*(80-70) = 70+5=75 ✓ YES!
        # So band pct = poor→60, fair→70, good→80, excellent→90, outstanding→100
        result = engine.calculate_raw_score(Decimal("65"), ASCENDING_THRESHOLDS)
        assert result == Decimal("75.00")

    def test_at_exact_good_threshold_returns_80(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual exactly at Good threshold(70) → 80%."""
        result = engine.calculate_raw_score(Decimal("70"), ASCENDING_THRESHOLDS)
        assert result == Decimal("80.00")

    def test_at_exact_fair_threshold_returns_70(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual exactly at Fair threshold(60) → 70%."""
        result = engine.calculate_raw_score(Decimal("60"), ASCENDING_THRESHOLDS)
        assert result == Decimal("70.00")

    def test_at_exact_excellent_threshold_returns_90(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual exactly at Excellent threshold(80) → 90%."""
        result = engine.calculate_raw_score(Decimal("80"), ASCENDING_THRESHOLDS)
        assert result == Decimal("90.00")

    def test_at_exact_poor_threshold_returns_60(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual exactly at Poor threshold(50) → 60%."""
        result = engine.calculate_raw_score(Decimal("50"), ASCENDING_THRESHOLDS)
        assert result == Decimal("60.00")

    def test_below_poor_threshold_proportional(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual=25 below poor threshold=50 → proportional below 60%."""
        # actual=25, poor=50, proportional: (25/50) * 60 = 30%
        result = engine.calculate_raw_score(Decimal("25"), ASCENDING_THRESHOLDS)
        assert result == Decimal("30.00")

    def test_zero_actual_returns_zero(self, engine: OHCSFScoringEngine) -> None:
        """Actual=0 → 0%."""
        result = engine.calculate_raw_score(Decimal("0"), ASCENDING_THRESHOLDS)
        assert result == Decimal("0.00")

    def test_between_good_and_excellent(self, engine: OHCSFScoringEngine) -> None:
        """Actual=75 between good(70) and excellent(80) → 85%."""
        # 80 + (5/10)*(90-80) = 80 + 5 = 85
        result = engine.calculate_raw_score(Decimal("75"), ASCENDING_THRESHOLDS)
        assert result == Decimal("85.00")

    def test_between_excellent_and_outstanding(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Actual=83 between excellent(80) and outstanding(85) → 96%."""
        # 90 + (3/5)*(100-90) = 90 + 6 = 96
        result = engine.calculate_raw_score(Decimal("83"), ASCENDING_THRESHOLDS)
        assert result == Decimal("96.00")

    def test_between_poor_and_fair(self, engine: OHCSFScoringEngine) -> None:
        """Actual=55 between poor(50) and fair(60) → 65%."""
        # 60 + (5/10)*(70-60) = 60 + 5 = 65
        result = engine.calculate_raw_score(Decimal("55"), ASCENDING_THRESHOLDS)
        assert result == Decimal("65.00")

    def test_inverse_thresholds_lower_is_better(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Error rate: out=0.5, exc=1, good=2, fair=4, poor=6, actual=1.8 → ~82%."""
        # actual=1.8 between good(2) and excellent(1)
        # For descending: lower threshold value = excellent=1, upper = good=2
        # (1.8 is closer to good=2, so closer to 80% band)
        # score = 80 + ((2-1.8)/(2-1)) * (90-80) = 80 + (0.2/1)*10 = 80 + 2 = 82
        result = engine.calculate_raw_score(Decimal("1.8"), DESCENDING_THRESHOLDS)
        assert result == Decimal("82.00")

    def test_inverse_at_outstanding_threshold(self, engine: OHCSFScoringEngine) -> None:
        """Error rate at or below outstanding threshold → 100%."""
        result = engine.calculate_raw_score(Decimal("0.5"), DESCENDING_THRESHOLDS)
        assert result == Decimal("100.00")

    def test_inverse_below_outstanding_threshold(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Error rate better than outstanding threshold → 100%."""
        result = engine.calculate_raw_score(Decimal("0.2"), DESCENDING_THRESHOLDS)
        assert result == Decimal("100.00")

    def test_inverse_above_poor_threshold(self, engine: OHCSFScoringEngine) -> None:
        """Error rate worse than poor threshold → proportional below 60%."""
        # actual=9, poor=6, proportional: (6/9)*60 = 40
        result = engine.calculate_raw_score(Decimal("9"), DESCENDING_THRESHOLDS)
        assert result == Decimal("40.00")

    def test_inverse_at_poor_threshold_returns_60(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Error rate exactly at poor threshold → 60%."""
        result = engine.calculate_raw_score(Decimal("6"), DESCENDING_THRESHOLDS)
        assert result == Decimal("60.00")

    def test_inverse_at_fair_threshold_returns_70(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Error rate exactly at fair threshold → 70%."""
        result = engine.calculate_raw_score(Decimal("4"), DESCENDING_THRESHOLDS)
        assert result == Decimal("70.00")

    def test_result_capped_at_100(self, engine: OHCSFScoringEngine) -> None:
        """Score never exceeds 100%."""
        result = engine.calculate_raw_score(Decimal("200"), ASCENDING_THRESHOLDS)
        assert result == Decimal("100.00")


class TestWeightedScore:
    """Tests for calculate_weighted_score()."""

    def test_weighted_calculation(self, engine: OHCSFScoringEngine) -> None:
        """75% × 0.50 = 37.50."""
        result = engine.calculate_weighted_score(Decimal("75"), Decimal("0.50"))
        assert result == Decimal("37.50")

    def test_weighted_100_percent_full_weight(self, engine: OHCSFScoringEngine) -> None:
        """100% × 1.0 = 100.00."""
        result = engine.calculate_weighted_score(Decimal("100"), Decimal("1.0"))
        assert result == Decimal("100.00")

    def test_weighted_zero_score(self, engine: OHCSFScoringEngine) -> None:
        """0% × 0.30 = 0.00."""
        result = engine.calculate_weighted_score(Decimal("0"), Decimal("0.30"))
        assert result == Decimal("0.00")

    def test_weighted_80_percent_30_weight(self, engine: OHCSFScoringEngine) -> None:
        """80% × 0.30 = 24.00."""
        result = engine.calculate_weighted_score(Decimal("80"), Decimal("0.30"))
        assert result == Decimal("24.00")

    def test_weighted_result_is_decimal(self, engine: OHCSFScoringEngine) -> None:
        """Result is always a Decimal."""
        result = engine.calculate_weighted_score(Decimal("66.67"), Decimal("0.20"))
        assert isinstance(result, Decimal)


class TestComposite:
    """Tests for calculate_composite()."""

    def test_composite_from_spec_example(self, engine: OHCSFScoringEngine) -> None:
        """From OHCSF guidelines worked example: [37.50, 24.00, 20.00] → 81.50."""
        weighted_scores = [Decimal("37.50"), Decimal("24.00"), Decimal("20.00")]
        result = engine.calculate_composite(weighted_scores)
        assert result == Decimal("81.50")

    def test_composite_single_score(self, engine: OHCSFScoringEngine) -> None:
        """Single weighted score returns that score."""
        result = engine.calculate_composite([Decimal("72.50")])
        assert result == Decimal("72.50")

    def test_composite_empty_list_returns_zero(
        self, engine: OHCSFScoringEngine
    ) -> None:
        """Empty list of weighted scores → 0.00."""
        result = engine.calculate_composite([])
        assert result == Decimal("0.00")

    def test_composite_with_fractional_scores(self, engine: OHCSFScoringEngine) -> None:
        """Fractional weighted scores are summed correctly."""
        weighted_scores = [Decimal("33.33"), Decimal("22.22"), Decimal("11.11")]
        result = engine.calculate_composite(weighted_scores)
        assert result == Decimal("66.66")

    def test_composite_max_score(self, engine: OHCSFScoringEngine) -> None:
        """Full scores sum to 100."""
        weighted_scores = [Decimal("60.00"), Decimal("25.00"), Decimal("15.00")]
        result = engine.calculate_composite(weighted_scores)
        assert result == Decimal("100.00")


class TestFinalScore:
    """Tests for calculate_appraisal_final()."""

    def test_final_appraisal_score(self, engine: OHCSFScoringEngine) -> None:
        """Example: objective=58.30(×0.70) + competency=80.00(×0.20) + process=80.00(×0.10) = 82.81."""
        # 58.30 * 0.70 = 40.81, 80.00 * 0.20 = 16.00, 80.00 * 0.10 = 8.00
        # Total = 64.81 -- that doesn't match "82.30" in task spec
        # Let me use the spec numbers directly: task says "58.30 + 16.00 + 8.00 = 82.30"
        # This means objective_composite is already the weighted contribution = 58.30
        # So the 0.70/0.20/0.10 weights are applied at the objective/competency/process composite level
        # BUT if objective_composite=83.28 * 0.70 = 58.30, competency=80 * 0.20=16, process=80 * 0.10=8
        # Final = 58.30 + 16.00 + 8.00 = 82.30
        # So the method takes the COMPOSITES (already 0-100 scale) and applies the 70/20/10 weighting
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("83.28"),
            competency_score=Decimal("80.00"),
            process_score=Decimal("80.00"),
        )
        # 83.28*0.70 = 58.296 → 58.30, 80*0.20=16.00, 80*0.10=8.00, total=82.30
        assert result == Decimal("82.30")

    def test_perfect_score(self, engine: OHCSFScoringEngine) -> None:
        """Perfect composites → final = 100.00."""
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("100"),
            competency_score=Decimal("100"),
            process_score=Decimal("100"),
        )
        assert result == Decimal("100.00")

    def test_zero_scores(self, engine: OHCSFScoringEngine) -> None:
        """All zeros → 0.00."""
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("0"),
            process_score=Decimal("0"),
        )
        assert result == Decimal("0.00")

    def test_weights_proportions(self, engine: OHCSFScoringEngine) -> None:
        """Only objective score → 70% of 100 = 70.00."""
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("100"),
            competency_score=Decimal("0"),
            process_score=Decimal("0"),
        )
        assert result == Decimal("70.00")

    def test_competency_only_weight(self, engine: OHCSFScoringEngine) -> None:
        """Only competency score → 20% of 100 = 20.00."""
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("100"),
            process_score=Decimal("0"),
        )
        assert result == Decimal("20.00")

    def test_process_only_weight(self, engine: OHCSFScoringEngine) -> None:
        """Only process score → 10% of 100 = 10.00."""
        result = engine.calculate_appraisal_final(
            objective_composite=Decimal("0"),
            competency_score=Decimal("0"),
            process_score=Decimal("100"),
        )
        assert result == Decimal("10.00")


class TestRatingLabel:
    """Tests for score_to_rating()."""

    @pytest.mark.parametrize(
        "score,expected_rating,expected_label",
        [
            (Decimal("95"), 5, "Outstanding"),
            (Decimal("90"), 5, "Outstanding"),
            (Decimal("85"), 4, "Excellent"),
            (Decimal("80"), 4, "Excellent"),
            (Decimal("75"), 3, "Good"),
            (Decimal("70"), 3, "Good"),
            (Decimal("65"), 2, "Fair"),
            (Decimal("60"), 2, "Fair"),
            (Decimal("55"), 1, "Poor"),
            (Decimal("0"), 1, "Poor"),
            (Decimal("59.99"), 1, "Poor"),
        ],
    )
    def test_rating_labels(
        self,
        engine: OHCSFScoringEngine,
        score: Decimal,
        expected_rating: int,
        expected_label: str,
    ) -> None:
        """Score maps to correct (rating_int, label) tuple."""
        rating, label = engine.score_to_rating(score)
        assert rating == expected_rating
        assert label == expected_label

    def test_score_to_rating_returns_tuple(self, engine: OHCSFScoringEngine) -> None:
        """Return type is a tuple of (int, str)."""
        result = engine.score_to_rating(Decimal("75"))
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], int)
        assert isinstance(result[1], str)


class TestRatingScaleConstant:
    """Tests for OHCSF_RATING_SCALE constant."""

    def test_has_five_ratings(self) -> None:
        """Rating scale has exactly 5 entries."""
        assert len(OHCSF_RATING_SCALE) == 5

    def test_all_expected_ratings_present(self) -> None:
        """All 5 ratings (1-5) are present."""
        for i in range(1, 6):
            assert i in OHCSF_RATING_SCALE

    def test_each_entry_has_label_and_min_pct(self) -> None:
        """Each rating entry has 'label' and 'min_pct' keys."""
        for rating, entry in OHCSF_RATING_SCALE.items():
            assert "label" in entry, f"Rating {rating} missing 'label'"
            assert "min_pct" in entry, f"Rating {rating} missing 'min_pct'"

    def test_labels_are_correct(self) -> None:
        """Labels match expected OHCSF names."""
        expected = {
            1: "Poor",
            2: "Fair",
            3: "Good",
            4: "Excellent",
            5: "Outstanding",
        }
        for rating, label in expected.items():
            assert OHCSF_RATING_SCALE[rating]["label"] == label

    def test_min_pcts_are_correct(self) -> None:
        """Minimum percentages match OHCSF scale."""
        assert OHCSF_RATING_SCALE[5]["min_pct"] == Decimal("90")
        assert OHCSF_RATING_SCALE[4]["min_pct"] == Decimal("80")
        assert OHCSF_RATING_SCALE[3]["min_pct"] == Decimal("70")
        assert OHCSF_RATING_SCALE[2]["min_pct"] == Decimal("60")
        assert OHCSF_RATING_SCALE[1]["min_pct"] == Decimal("0")

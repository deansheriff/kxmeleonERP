"""
Tests for PMS Config Service — seed data validation.

Tests focus on the DATA constants, not DB operations.
"""

from app.services.people.perf.pms_config_service import (
    OHCSF_COMPETENCIES,
    OHCSF_INSTITUTIONAL_WEIGHTS,
)

# ---------------------------------------------------------------------------
# OHCSF Competency seed data
# ---------------------------------------------------------------------------


def test_competency_seed_data_has_18_competencies() -> None:
    total = sum(len(comps) for comps in OHCSF_COMPETENCIES.values())
    assert total == 18


def test_competency_seed_data_has_5_clusters() -> None:
    assert len(OHCSF_COMPETENCIES) == 5


def test_competency_cluster_names() -> None:
    expected = {
        "ETHICS_AND_VALUES",
        "PEOPLE",
        "EXECUTION",
        "VISION",
        "EXPERTISE",
    }
    assert set(OHCSF_COMPETENCIES.keys()) == expected


def test_ethics_and_values_cluster_has_4_competencies() -> None:
    assert len(OHCSF_COMPETENCIES["ETHICS_AND_VALUES"]) == 4


def test_people_cluster_has_3_competencies() -> None:
    assert len(OHCSF_COMPETENCIES["PEOPLE"]) == 3


def test_execution_cluster_has_3_competencies() -> None:
    assert len(OHCSF_COMPETENCIES["EXECUTION"]) == 3


def test_vision_cluster_has_3_competencies() -> None:
    assert len(OHCSF_COMPETENCIES["VISION"]) == 3


def test_expertise_cluster_has_5_competencies() -> None:
    assert len(OHCSF_COMPETENCIES["EXPERTISE"]) == 5


def test_competency_codes_are_unique() -> None:
    all_codes = [code for comps in OHCSF_COMPETENCIES.values() for code, _ in comps]
    assert len(all_codes) == len(set(all_codes)), "Duplicate competency codes found"


def test_competency_codes_start_with_ohcsf_prefix() -> None:
    for cluster, comps in OHCSF_COMPETENCIES.items():
        for code, _name in comps:
            assert code.startswith("OHCSF-"), (
                f"Competency code {code!r} in cluster {cluster!r} "
                "does not start with 'OHCSF-'"
            )


def test_competency_codes_fit_model_length_limit() -> None:
    for cluster, comps in OHCSF_COMPETENCIES.items():
        for code, _name in comps:
            assert len(code) <= 20, (
                f"Competency code {code!r} in cluster {cluster!r} "
                "exceeds hr.competency.competency_code length limit"
            )


def test_competency_names_are_non_empty() -> None:
    for cluster, comps in OHCSF_COMPETENCIES.items():
        for code, name in comps:
            assert name.strip(), (
                f"Empty name for competency {code!r} in cluster {cluster!r}"
            )


def test_competency_entries_are_tuples_of_two() -> None:
    for cluster, comps in OHCSF_COMPETENCIES.items():
        for entry in comps:
            assert isinstance(entry, tuple) and len(entry) == 2, (
                f"Competency entry {entry!r} in cluster {cluster!r} "
                "is not a (code, name) tuple"
            )


# ---------------------------------------------------------------------------
# OHCSF Institutional Weights seed data
# ---------------------------------------------------------------------------


def test_institutional_weights_has_6_institution_types() -> None:
    assert len(OHCSF_INSTITUTIONAL_WEIGHTS) == 6


def test_institutional_weights_have_8_criteria_each() -> None:
    for inst_type, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
        assert len(criteria) == 8, (
            f"{inst_type} has {len(criteria)} criteria, expected 8"
        )


def test_institutional_weights_sum_to_100() -> None:
    for inst_type, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
        total = sum(weight for _, weight in criteria)
        assert total == 100, f"{inst_type} weights sum to {total}, expected 100"


def test_institutional_weights_institution_types() -> None:
    expected = {
        "MINISTRY",
        "REGULATORY",
        "GENERAL_SERVICES",
        "INFRASTRUCTURE",
        "SECURITY",
        "GOVT_COMPANY",
    }
    assert set(OHCSF_INSTITUTIONAL_WEIGHTS.keys()) == expected


def test_institutional_weights_criteria_are_positive() -> None:
    for inst_type, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
        for name, weight in criteria:
            assert weight > 0, (
                f"Weight for {name!r} in {inst_type} is {weight}, must be > 0"
            )


def test_institutional_weights_criteria_names_non_empty() -> None:
    for inst_type, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
        for name, _weight in criteria:
            assert name.strip(), f"Empty criteria name in {inst_type}"


def test_institutional_weights_entries_are_tuples_of_two() -> None:
    for inst_type, criteria in OHCSF_INSTITUTIONAL_WEIGHTS.items():
        for entry in criteria:
            assert isinstance(entry, tuple) and len(entry) == 2, (
                f"Entry {entry!r} in {inst_type} is not a (name, weight) tuple"
            )


def test_institutional_weights_all_share_same_criteria_names() -> None:
    """All institution types should assess the same 8 criteria names."""
    all_name_sets = [
        frozenset(name for name, _ in criteria)
        for criteria in OHCSF_INSTITUTIONAL_WEIGHTS.values()
    ]
    first = all_name_sets[0]
    for name_set in all_name_sets[1:]:
        assert name_set == first, "Institution types have differing criteria names"


def test_ministry_specific_weights() -> None:
    """Spot-check MINISTRY weights against the specification."""
    ministry = dict(OHCSF_INSTITUTIONAL_WEIGHTS["MINISTRY"])
    assert ministry["Government prioritized objectives"] == 25
    assert ministry["MDA Operational Objectives"] == 25
    assert ministry["Stakeholder Engagement"] == 10
    assert ministry["Staff Welfare"] == 5


def test_security_specific_weights() -> None:
    """Spot-check SECURITY weights against the specification."""
    security = dict(OHCSF_INSTITUTIONAL_WEIGHTS["SECURITY"])
    assert security["MDA Operational Objectives"] == 25
    assert security["Capacity Building & Talent Management"] == 10
    assert security["Automated Service Delivery"] == 5
    assert security["Support for Service Delivery"] == 20

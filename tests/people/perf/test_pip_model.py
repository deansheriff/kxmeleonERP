"""
Test suite for PerformanceImprovementPlan model.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid
from datetime import date

from app.models.people.perf.pip import PerformanceImprovementPlan
from app.models.people.perf.pms_enums import PIPCauseCategory, PIPOutcome, PIPStatus


class TestPIPInstantiation:
    """Tests for model instantiation with required fields."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        supervisor_id = uuid.uuid4()
        hr_officer_id = uuid.uuid4()

        pip = PerformanceImprovementPlan(
            organization_id=org_id,
            employee_id=employee_id,
            supervisor_id=supervisor_id,
            hr_officer_id=hr_officer_id,
            pip_code="PIP-2026-001",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 4, 1),
            reason="Consistent failure to meet KPIs",
            cause_category=PIPCauseCategory.SKILLS,
            improvement_areas=[
                {"area": "Time management", "target": "Submit reports on time"}
            ],
        )

        assert pip.organization_id == org_id
        assert pip.employee_id == employee_id
        assert pip.supervisor_id == supervisor_id
        assert pip.hr_officer_id == hr_officer_id
        assert pip.pip_code == "PIP-2026-001"
        assert pip.cause_category == PIPCauseCategory.SKILLS
        assert len(pip.improvement_areas) == 1

    def test_repr(self):
        """Model has a meaningful __repr__."""
        pip = PerformanceImprovementPlan(pip_code="PIP-2026-001")
        assert "PIP-2026-001" in repr(pip)


class TestPIPDefaults:
    """Tests for default field values."""

    def test_default_status_is_draft(self):
        """Status column has DRAFT as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceImprovementPlan)
        col = mapper.columns["status"]
        assert col.default is not None
        assert col.default.arg == PIPStatus.DRAFT

    def test_pip_id_column_has_uuid_default(self):
        """pip_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceImprovementPlan)
        col = mapper.columns["pip_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_extension_granted_default_false(self):
        """extension_granted column has False as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceImprovementPlan)
        col = mapper.columns["extension_granted"]
        assert col.default is not None
        assert col.default.arg is False

    def test_completion_letter_issued_default_false(self):
        """completion_letter_issued column has False as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(PerformanceImprovementPlan)
        col = mapper.columns["completion_letter_issued"]
        assert col.default is not None
        assert col.default.arg is False

    def test_outcome_default_none(self):
        """outcome defaults to None."""
        pip = PerformanceImprovementPlan()
        assert pip.outcome is None

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None."""
        pip = PerformanceImprovementPlan()
        assert pip.appraisal_id is None
        assert pip.support_measures is None
        assert pip.review_intervals is None
        assert pip.extension_end_date is None
        assert pip.extension_reason is None
        assert pip.outcome is None
        assert pip.outcome_date is None
        assert pip.outcome_notes is None
        assert pip.escalation_action is None
        assert pip.committee_referral_date is None
        assert pip.committee_decision is None
        assert pip.updated_at is None


class TestPIPTableConfig:
    """Tests for SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'performance_improvement_plan'."""
        assert (
            PerformanceImprovementPlan.__tablename__ == "performance_improvement_plan"
        )

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = PerformanceImprovementPlan.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_unique_constraint_exists(self):
        """UniqueConstraint on organization_id + pip_code exists."""
        from sqlalchemy import UniqueConstraint

        table_args = PerformanceImprovementPlan.__table_args__
        constraints = [a for a in table_args if isinstance(a, UniqueConstraint)]
        assert len(constraints) == 1
        uc = constraints[0]
        assert uc.name == "uq_pip_code"

    def test_indexes_exist(self):
        """All required indexes are declared."""
        from sqlalchemy import Index

        table_args = PerformanceImprovementPlan.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_pip_employee" in index_names
        assert "idx_pip_org_status" in index_names


class TestPIPFields:
    """Tests for individual field properties."""

    def test_status_accepts_all_pip_status_values(self):
        """status accepts all PIPStatus enum values."""
        for s in PIPStatus:
            pip = PerformanceImprovementPlan(status=s)
            assert pip.status == s

    def test_cause_category_accepts_all_values(self):
        """cause_category accepts all PIPCauseCategory enum values."""
        for cat in PIPCauseCategory:
            pip = PerformanceImprovementPlan(cause_category=cat)
            assert pip.cause_category == cat

    def test_outcome_accepts_all_pip_outcome_values(self):
        """outcome accepts all PIPOutcome enum values."""
        for o in PIPOutcome:
            pip = PerformanceImprovementPlan(outcome=o)
            assert pip.outcome == o

    def test_improvement_areas_accepts_list(self):
        """improvement_areas accepts a list of dicts."""
        areas = [
            {"area": "Communication", "target": "No missed deadlines"},
            {"area": "Attendance", "target": "< 2 absences per month"},
        ]
        pip = PerformanceImprovementPlan(improvement_areas=areas)
        assert pip.improvement_areas == areas

    def test_review_intervals_accepts_json(self):
        """review_intervals accepts a JSON-serialisable value."""
        intervals = [
            {"week": 2, "type": "check-in"},
            {"week": 6, "type": "formal-review"},
        ]
        pip = PerformanceImprovementPlan(review_intervals=intervals)
        assert pip.review_intervals == intervals

    def test_pip_code_accepts_string(self):
        """pip_code accepts a string value up to 30 chars."""
        pip = PerformanceImprovementPlan(pip_code="PIP-2026-001")
        assert pip.pip_code == "PIP-2026-001"

    def test_appraisal_id_accepts_uuid(self):
        """appraisal_id accepts a UUID."""
        appraisal_id = uuid.uuid4()
        pip = PerformanceImprovementPlan(appraisal_id=appraisal_id)
        assert pip.appraisal_id == appraisal_id

    def test_extension_fields_accept_values(self):
        """Extension fields accept appropriate values."""
        pip = PerformanceImprovementPlan(
            extension_granted=True,
            extension_end_date=date(2026, 7, 1),
            extension_reason="Employee requested additional time",
        )
        assert pip.extension_granted is True
        assert pip.extension_end_date == date(2026, 7, 1)
        assert pip.extension_reason == "Employee requested additional time"

    def test_committee_fields_accept_values(self):
        """Committee fields accept appropriate values."""
        pip = PerformanceImprovementPlan(
            committee_referral_date=date(2026, 5, 1),
            committee_decision="Proceed to disciplinary action",
        )
        assert pip.committee_referral_date == date(2026, 5, 1)
        assert pip.committee_decision == "Proceed to disciplinary action"

    def test_escalation_action_accepts_string(self):
        """escalation_action accepts a string."""
        pip = PerformanceImprovementPlan(escalation_action="DISCIPLINARY")
        assert pip.escalation_action == "DISCIPLINARY"


class TestPIPRelationships:
    """Tests for relationship declarations on the model."""

    def test_employee_relationship_declared(self):
        """'employee' relationship is declared."""
        assert hasattr(PerformanceImprovementPlan, "employee")

    def test_supervisor_relationship_declared(self):
        """'supervisor' relationship is declared."""
        assert hasattr(PerformanceImprovementPlan, "supervisor")

    def test_hr_officer_relationship_declared(self):
        """'hr_officer' relationship is declared."""
        assert hasattr(PerformanceImprovementPlan, "hr_officer")

    def test_appraisal_relationship_declared(self):
        """'appraisal' relationship is declared."""
        assert hasattr(PerformanceImprovementPlan, "appraisal")


class TestPIPInheritance:
    """Tests for proper base class inheritance."""

    def test_inherits_audit_mixin(self):
        """PerformanceImprovementPlan inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(PerformanceImprovementPlan(), AuditMixin)

    def test_audit_mixin_fields_present(self):
        """AuditMixin fields (created_by_id, updated_by_id) are present."""
        pip = PerformanceImprovementPlan()
        assert hasattr(pip, "created_by_id")
        assert hasattr(pip, "updated_by_id")

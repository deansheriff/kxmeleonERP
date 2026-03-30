"""
Test suite for CompetencyAssessment, StrategicObjective, and AppraisalOutcomeAction models.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid
from datetime import date

from app.models.people.perf.appraisal_outcome_action import AppraisalOutcomeAction
from app.models.people.perf.competency_assessment import CompetencyAssessment
from app.models.people.perf.pms_enums import OutcomeActionStatus, OutcomeActionType
from app.models.people.perf.strategic_objective import StrategicObjective

# ---------------------------------------------------------------------------
# CompetencyAssessment
# ---------------------------------------------------------------------------


class TestCompetencyAssessmentInstantiation:
    """Tests for CompetencyAssessment model instantiation."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        appraisal_id = uuid.uuid4()
        competency_id = uuid.uuid4()

        assessment = CompetencyAssessment(
            organization_id=org_id,
            appraisal_id=appraisal_id,
            competency_id=competency_id,
        )

        assert assessment.organization_id == org_id
        assert assessment.appraisal_id == appraisal_id
        assert assessment.competency_id == competency_id

    def test_repr(self):
        """Model has a meaningful __repr__."""
        appraisal_id = uuid.uuid4()
        competency_id = uuid.uuid4()
        assessment = CompetencyAssessment(
            appraisal_id=appraisal_id,
            competency_id=competency_id,
        )
        r = repr(assessment)
        assert "CompetencyAssessment" in r


class TestCompetencyAssessmentDefaults:
    """Tests for CompetencyAssessment default field values."""

    def test_assessment_id_has_uuid_default(self):
        """assessment_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(CompetencyAssessment)
        col = mapper.columns["assessment_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_is_priority_defaults_false(self):
        """is_priority defaults to False."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(CompetencyAssessment)
        col = mapper.columns["is_priority"]
        assert col.default is not None
        assert col.default.arg is False

    def test_is_development_focus_defaults_false(self):
        """is_development_focus defaults to False."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(CompetencyAssessment)
        col = mapper.columns["is_development_focus"]
        assert col.default is not None
        assert col.default.arg is False

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None on a new instance."""
        assessment = CompetencyAssessment()
        assert assessment.target_proficiency is None
        assert assessment.self_rating is None
        assert assessment.manager_rating is None
        assert assessment.final_rating is None
        assert assessment.evidence is None
        assert assessment.updated_at is None


class TestCompetencyAssessmentTableConfig:
    """Tests for CompetencyAssessment table configuration."""

    def test_table_name(self):
        """Table name is 'competency_assessment'."""
        assert CompetencyAssessment.__tablename__ == "competency_assessment"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = CompetencyAssessment.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_index_on_appraisal_id_exists(self):
        """Index on appraisal_id is declared."""
        from sqlalchemy import Index

        table_args = CompetencyAssessment.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_comp_assess_appraisal" in index_names

    def test_does_not_inherit_audit_mixin(self):
        """CompetencyAssessment does NOT inherit from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert not isinstance(CompetencyAssessment(), AuditMixin)


class TestCompetencyAssessmentFields:
    """Tests for individual CompetencyAssessment field properties."""

    def test_boolean_flags_can_be_set_true(self):
        """is_priority and is_development_focus accept True."""
        assessment = CompetencyAssessment(is_priority=True, is_development_focus=True)
        assert assessment.is_priority is True
        assert assessment.is_development_focus is True

    def test_integer_rating_fields_accept_values(self):
        """Integer rating fields accept integer values."""
        assessment = CompetencyAssessment(
            target_proficiency=3,
            self_rating=4,
            manager_rating=3,
            final_rating=4,
        )
        assert assessment.target_proficiency == 3
        assert assessment.self_rating == 4
        assert assessment.manager_rating == 3
        assert assessment.final_rating == 4

    def test_evidence_accepts_text(self):
        """evidence field accepts text."""
        assessment = CompetencyAssessment(evidence="Demonstrated leadership in project")
        assert assessment.evidence == "Demonstrated leadership in project"


class TestCompetencyAssessmentRelationships:
    """Tests for CompetencyAssessment relationship declarations."""

    def test_appraisal_relationship_declared(self):
        """'appraisal' relationship is declared."""
        assert hasattr(CompetencyAssessment, "appraisal")

    def test_competency_relationship_declared(self):
        """'competency' relationship is declared."""
        assert hasattr(CompetencyAssessment, "competency")


# ---------------------------------------------------------------------------
# StrategicObjective
# ---------------------------------------------------------------------------


class TestStrategicObjectiveInstantiation:
    """Tests for StrategicObjective model instantiation."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        cycle_id = uuid.uuid4()

        obj = StrategicObjective(
            organization_id=org_id,
            cycle_id=cycle_id,
            objective_code="SO-001",
            description="Improve service delivery by 20%",
        )

        assert obj.organization_id == org_id
        assert obj.cycle_id == cycle_id
        assert obj.objective_code == "SO-001"
        assert obj.description == "Improve service delivery by 20%"

    def test_repr(self):
        """Model has a meaningful __repr__."""
        obj = StrategicObjective(objective_code="SO-001")
        r = repr(obj)
        assert "StrategicObjective" in r


class TestStrategicObjectiveDefaults:
    """Tests for StrategicObjective default field values."""

    def test_objective_id_has_uuid_default(self):
        """objective_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(StrategicObjective)
        col = mapper.columns["objective_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_sequence_defaults_to_zero(self):
        """sequence column has a Python-level default of 0."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(StrategicObjective)
        col = mapper.columns["sequence"]
        assert col.default is not None
        assert col.default.arg == 0

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None on a new instance."""
        obj = StrategicObjective()
        assert obj.department_id is None
        assert obj.parent_objective_id is None
        assert obj.source_document is None
        assert obj.target_description is None
        assert obj.weight is None
        assert obj.updated_at is None


class TestStrategicObjectiveTableConfig:
    """Tests for StrategicObjective table configuration."""

    def test_table_name(self):
        """Table name is 'strategic_objective'."""
        assert StrategicObjective.__tablename__ == "strategic_objective"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = StrategicObjective.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_unique_constraint_on_org_and_code(self):
        """UniqueConstraint on organization_id + objective_code exists."""
        from sqlalchemy import UniqueConstraint

        table_args = StrategicObjective.__table_args__
        constraints = [a for a in table_args if isinstance(a, UniqueConstraint)]
        assert len(constraints) == 1
        uc = constraints[0]
        assert uc.name == "uq_strategic_obj_code"

    def test_indexes_exist(self):
        """All required indexes are declared."""
        from sqlalchemy import Index

        table_args = StrategicObjective.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_strat_obj_cycle" in index_names
        assert "idx_strat_obj_dept" in index_names

    def test_inherits_audit_mixin(self):
        """StrategicObjective inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(StrategicObjective(), AuditMixin)


class TestStrategicObjectiveFields:
    """Tests for individual StrategicObjective field properties."""

    def test_objective_code_accepts_string(self):
        """objective_code accepts a string value."""
        obj = StrategicObjective(objective_code="SO-2026-001")
        assert obj.objective_code == "SO-2026-001"

    def test_weight_accepts_decimal(self):
        """weight accepts a decimal value."""
        from decimal import Decimal

        obj = StrategicObjective(weight=Decimal("25.50"))
        assert obj.weight == Decimal("25.50")

    def test_source_document_accepts_string(self):
        """source_document accepts a string value."""
        obj = StrategicObjective(source_document="State Development Plan 2026-2030")
        assert obj.source_document == "State Development Plan 2026-2030"

    def test_sequence_accepts_integer(self):
        """sequence accepts an integer."""
        obj = StrategicObjective(sequence=5)
        assert obj.sequence == 5


class TestStrategicObjectiveRelationships:
    """Tests for StrategicObjective relationship declarations."""

    def test_cycle_relationship_declared(self):
        """'cycle' relationship is declared."""
        assert hasattr(StrategicObjective, "cycle")

    def test_parent_objective_relationship_declared(self):
        """'parent_objective' self-referential relationship is declared."""
        assert hasattr(StrategicObjective, "parent_objective")


# ---------------------------------------------------------------------------
# AppraisalOutcomeAction
# ---------------------------------------------------------------------------


class TestAppraisalOutcomeActionInstantiation:
    """Tests for AppraisalOutcomeAction model instantiation."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        appraisal_id = uuid.uuid4()

        action = AppraisalOutcomeAction(
            organization_id=org_id,
            appraisal_id=appraisal_id,
            action_type=OutcomeActionType.TRAINING,
        )

        assert action.organization_id == org_id
        assert action.appraisal_id == appraisal_id
        assert action.action_type == OutcomeActionType.TRAINING

    def test_repr(self):
        """Model has a meaningful __repr__."""
        action = AppraisalOutcomeAction(action_type=OutcomeActionType.REWARD)
        r = repr(action)
        assert "AppraisalOutcomeAction" in r


class TestAppraisalOutcomeActionDefaults:
    """Tests for AppraisalOutcomeAction default field values."""

    def test_action_id_has_uuid_default(self):
        """action_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(AppraisalOutcomeAction)
        col = mapper.columns["action_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_status_defaults_to_pending(self):
        """status column has PENDING as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(AppraisalOutcomeAction)
        col = mapper.columns["status"]
        assert col.default is not None
        assert col.default.arg == OutcomeActionStatus.PENDING

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None on a new instance."""
        action = AppraisalOutcomeAction()
        assert action.description is None
        assert action.actioned_by_id is None
        assert action.actioned_date is None
        assert action.reference_id is None
        assert action.reference_type is None
        assert action.notes is None
        assert action.updated_at is None


class TestAppraisalOutcomeActionTableConfig:
    """Tests for AppraisalOutcomeAction table configuration."""

    def test_table_name(self):
        """Table name is 'appraisal_outcome_action'."""
        assert AppraisalOutcomeAction.__tablename__ == "appraisal_outcome_action"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = AppraisalOutcomeAction.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_index_on_appraisal_id_exists(self):
        """Index on appraisal_id is declared."""
        from sqlalchemy import Index

        table_args = AppraisalOutcomeAction.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_outcome_appraisal" in index_names

    def test_inherits_audit_mixin(self):
        """AppraisalOutcomeAction inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(AppraisalOutcomeAction(), AuditMixin)


class TestAppraisalOutcomeActionFields:
    """Tests for individual AppraisalOutcomeAction field properties."""

    def test_action_type_accepts_all_enum_values(self):
        """action_type accepts all OutcomeActionType enum values."""
        for action_type in OutcomeActionType:
            action = AppraisalOutcomeAction(action_type=action_type)
            assert action.action_type == action_type

    def test_status_accepts_all_enum_values(self):
        """status accepts all OutcomeActionStatus enum values."""
        for status in OutcomeActionStatus:
            action = AppraisalOutcomeAction(status=status)
            assert action.status == status

    def test_actioned_date_accepts_date(self):
        """actioned_date accepts a date value."""
        d = date(2026, 3, 15)
        action = AppraisalOutcomeAction(actioned_date=d)
        assert action.actioned_date == d

    def test_reference_id_accepts_uuid(self):
        """reference_id accepts a UUID value (no FK constraint)."""
        ref_id = uuid.uuid4()
        action = AppraisalOutcomeAction(reference_id=ref_id)
        assert action.reference_id == ref_id

    def test_reference_type_accepts_string(self):
        """reference_type accepts a string value."""
        action = AppraisalOutcomeAction(reference_type="training_program")
        assert action.reference_type == "training_program"

    def test_notes_accepts_text(self):
        """notes accepts multiline text."""
        notes = (
            "Enrolled in leadership development program\nExpected completion: June 2026"
        )
        action = AppraisalOutcomeAction(notes=notes)
        assert action.notes == notes


class TestAppraisalOutcomeActionRelationships:
    """Tests for AppraisalOutcomeAction relationship declarations."""

    def test_appraisal_relationship_declared(self):
        """'appraisal' relationship is declared."""
        assert hasattr(AppraisalOutcomeAction, "appraisal")

    def test_actioned_by_relationship_declared(self):
        """'actioned_by' relationship is declared."""
        assert hasattr(AppraisalOutcomeAction, "actioned_by")

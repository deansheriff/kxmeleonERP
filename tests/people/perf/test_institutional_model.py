"""
Test suite for InstitutionalPerformance and InstitutionalCriteriaTemplate models.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid

from app.models.people.perf.institutional_performance import (
    InstitutionalCriteriaTemplate,
    InstitutionalPerformance,
)
from app.models.people.perf.pms_enums import (
    InstitutionalPerfStatus,
    InstitutionType,
)

# ---------------------------------------------------------------------------
# InstitutionalPerformance
# ---------------------------------------------------------------------------


class TestInstitutionalPerformanceInstantiation:
    """Tests for InstitutionalPerformance instantiation with required fields."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        cycle_id = uuid.uuid4()

        inst_perf = InstitutionalPerformance(
            organization_id=org_id,
            cycle_id=cycle_id,
            institution_type=InstitutionType.MINISTRY,
        )

        assert inst_perf.organization_id == org_id
        assert inst_perf.cycle_id == cycle_id
        assert inst_perf.institution_type == InstitutionType.MINISTRY

    def test_repr(self):
        """Model has a meaningful __repr__."""
        inst_perf = InstitutionalPerformance(
            institution_type=InstitutionType.REGULATORY,
            status=InstitutionalPerfStatus.DRAFT,
        )
        r = repr(inst_perf)
        assert "REGULATORY" in r
        assert "DRAFT" in r


class TestInstitutionalPerformanceDefaults:
    """Tests for InstitutionalPerformance default field values."""

    def test_default_status_is_draft(self):
        """status column has DRAFT as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(InstitutionalPerformance)
        col = mapper.columns["status"]
        assert col.default is not None
        assert col.default.arg == InstitutionalPerfStatus.DRAFT

    def test_default_is_reconciled_is_false(self):
        """is_reconciled column has False as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(InstitutionalPerformance)
        col = mapper.columns["is_reconciled"]
        assert col.default is not None
        assert col.default.arg is False

    def test_inst_perf_id_has_uuid_default(self):
        """inst_perf_id column has a callable default (uuid4)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(InstitutionalPerformance)
        col = mapper.columns["inst_perf_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None."""
        inst_perf = InstitutionalPerformance()
        assert inst_perf.department_id is None
        assert inst_perf.criteria_scores is None
        assert inst_perf.composite_score is None
        assert inst_perf.rating_label is None
        assert inst_perf.reviewed_by_id is None
        assert inst_perf.review_date is None
        assert inst_perf.notes is None
        assert inst_perf.pre_reconciliation_composite is None
        assert inst_perf.reconciled_by_id is None
        assert inst_perf.reconciliation_date is None
        assert inst_perf.reconciliation_notes is None
        assert inst_perf.updated_at is None


class TestInstitutionalPerformanceTableConfig:
    """Tests for InstitutionalPerformance SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'institutional_performance'."""
        assert InstitutionalPerformance.__tablename__ == "institutional_performance"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = InstitutionalPerformance.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_indexes_exist(self):
        """Required indexes are declared."""
        from sqlalchemy import Index

        table_args = InstitutionalPerformance.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_inst_perf_cycle" in index_names
        assert "idx_inst_perf_dept" in index_names


class TestInstitutionalPerformanceFields:
    """Tests for individual field properties of InstitutionalPerformance."""

    def test_institution_type_accepts_all_enum_values(self):
        """institution_type accepts all InstitutionType enum values."""
        for it in InstitutionType:
            inst_perf = InstitutionalPerformance(institution_type=it)
            assert inst_perf.institution_type == it

    def test_status_accepts_all_enum_values(self):
        """status accepts all InstitutionalPerfStatus enum values."""
        for s in InstitutionalPerfStatus:
            inst_perf = InstitutionalPerformance(status=s)
            assert inst_perf.status == s

    def test_criteria_scores_accepts_dict(self):
        """criteria_scores accepts a JSON-compatible dict."""
        scores = {"quality": 85, "timeliness": 90}
        inst_perf = InstitutionalPerformance(criteria_scores=scores)
        assert inst_perf.criteria_scores == scores

    def test_rating_label_accepts_string(self):
        """rating_label accepts a short string."""
        inst_perf = InstitutionalPerformance(rating_label="Excellent")
        assert inst_perf.rating_label == "Excellent"

    def test_notes_accepts_text(self):
        """notes accepts multiline text."""
        notes = "Line 1\nLine 2"
        inst_perf = InstitutionalPerformance(notes=notes)
        assert inst_perf.notes == notes

    def test_reconciliation_notes_accepts_text(self):
        """reconciliation_notes accepts text."""
        inst_perf = InstitutionalPerformance(reconciliation_notes="Adjusted score")
        assert inst_perf.reconciliation_notes == "Adjusted score"

    def test_is_reconciled_can_be_set_true(self):
        """is_reconciled can be set to True."""
        inst_perf = InstitutionalPerformance(is_reconciled=True)
        assert inst_perf.is_reconciled is True

    def test_reviewed_by_id_accepts_uuid(self):
        """reviewed_by_id accepts a UUID."""
        emp_id = uuid.uuid4()
        inst_perf = InstitutionalPerformance(reviewed_by_id=emp_id)
        assert inst_perf.reviewed_by_id == emp_id

    def test_reconciled_by_id_accepts_uuid(self):
        """reconciled_by_id accepts a UUID."""
        emp_id = uuid.uuid4()
        inst_perf = InstitutionalPerformance(reconciled_by_id=emp_id)
        assert inst_perf.reconciled_by_id == emp_id

    def test_department_id_accepts_uuid(self):
        """department_id accepts a UUID."""
        dept_id = uuid.uuid4()
        inst_perf = InstitutionalPerformance(department_id=dept_id)
        assert inst_perf.department_id == dept_id


class TestInstitutionalPerformanceRelationships:
    """Tests for relationship declarations on InstitutionalPerformance."""

    def test_cycle_relationship_declared(self):
        """'cycle' relationship is declared."""
        assert hasattr(InstitutionalPerformance, "cycle")

    def test_reviewed_by_relationship_declared(self):
        """'reviewed_by' relationship is declared."""
        assert hasattr(InstitutionalPerformance, "reviewed_by")

    def test_reconciled_by_relationship_declared(self):
        """'reconciled_by' relationship is declared."""
        assert hasattr(InstitutionalPerformance, "reconciled_by")


class TestInstitutionalPerformanceInheritance:
    """Tests for proper base class inheritance."""

    def test_inherits_audit_mixin(self):
        """InstitutionalPerformance inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(InstitutionalPerformance(), AuditMixin)

    def test_audit_mixin_fields_present(self):
        """AuditMixin fields are present."""
        inst_perf = InstitutionalPerformance()
        assert hasattr(inst_perf, "created_by_id")
        assert hasattr(inst_perf, "updated_by_id")


# ---------------------------------------------------------------------------
# InstitutionalCriteriaTemplate
# ---------------------------------------------------------------------------


class TestInstitutionalCriteriaTemplateInstantiation:
    """Tests for InstitutionalCriteriaTemplate instantiation."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()

        tmpl = InstitutionalCriteriaTemplate(
            organization_id=org_id,
            institution_type=InstitutionType.MINISTRY,
            criteria_name="Budget Execution",
            default_weight=25,
            sequence=1,
        )

        assert tmpl.organization_id == org_id
        assert tmpl.institution_type == InstitutionType.MINISTRY
        assert tmpl.criteria_name == "Budget Execution"
        assert tmpl.default_weight == 25
        assert tmpl.sequence == 1

    def test_repr(self):
        """Model has a meaningful __repr__."""
        tmpl = InstitutionalCriteriaTemplate(
            criteria_name="Service Delivery",
            institution_type=InstitutionType.REGULATORY,
        )
        r = repr(tmpl)
        assert "Service Delivery" in r
        assert "REGULATORY" in r


class TestInstitutionalCriteriaTemplateDefaults:
    """Tests for InstitutionalCriteriaTemplate default field values."""

    def test_default_is_active_is_true(self):
        """is_active column has True as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(InstitutionalCriteriaTemplate)
        col = mapper.columns["is_active"]
        assert col.default is not None
        assert col.default.arg is True

    def test_template_id_has_uuid_default(self):
        """template_id column has a callable default (uuid4)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(InstitutionalCriteriaTemplate)
        col = mapper.columns["template_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_is_active_can_be_set_false(self):
        """is_active can be explicitly set to False."""
        tmpl = InstitutionalCriteriaTemplate(is_active=False)
        assert tmpl.is_active is False


class TestInstitutionalCriteriaTemplateTableConfig:
    """Tests for InstitutionalCriteriaTemplate SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'institutional_criteria_template'."""
        assert (
            InstitutionalCriteriaTemplate.__tablename__
            == "institutional_criteria_template"
        )

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = InstitutionalCriteriaTemplate.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_index_exists(self):
        """Required index is declared."""
        from sqlalchemy import Index

        table_args = InstitutionalCriteriaTemplate.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_criteria_tmpl_type" in index_names


class TestInstitutionalCriteriaTemplateFields:
    """Tests for individual field properties of InstitutionalCriteriaTemplate."""

    def test_institution_type_accepts_all_enum_values(self):
        """institution_type accepts all InstitutionType enum values."""
        for it in InstitutionType:
            tmpl = InstitutionalCriteriaTemplate(institution_type=it)
            assert tmpl.institution_type == it

    def test_criteria_name_accepts_string(self):
        """criteria_name accepts a string value."""
        tmpl = InstitutionalCriteriaTemplate(criteria_name="Policy Implementation")
        assert tmpl.criteria_name == "Policy Implementation"

    def test_default_weight_accepts_integer(self):
        """default_weight accepts integer value."""
        tmpl = InstitutionalCriteriaTemplate(default_weight=20)
        assert tmpl.default_weight == 20

    def test_sequence_accepts_integer(self):
        """sequence accepts integer value."""
        tmpl = InstitutionalCriteriaTemplate(sequence=3)
        assert tmpl.sequence == 3


class TestInstitutionalCriteriaTemplateInheritance:
    """Tests for proper base class of InstitutionalCriteriaTemplate."""

    def test_does_not_inherit_audit_mixin(self):
        """InstitutionalCriteriaTemplate does NOT inherit from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert not isinstance(InstitutionalCriteriaTemplate(), AuditMixin)

    def test_no_created_by_field(self):
        """created_by_id is NOT present (no AuditMixin)."""
        tmpl = InstitutionalCriteriaTemplate()
        assert not hasattr(tmpl, "created_by_id")

    def test_has_created_at(self):
        """created_at field IS present on the model."""
        assert hasattr(InstitutionalCriteriaTemplate, "created_at")

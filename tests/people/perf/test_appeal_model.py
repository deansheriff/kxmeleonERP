"""
Test suite for AppraisalAppeal model.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid
from datetime import date

from app.models.people.perf.appraisal_appeal import AppraisalAppeal
from app.models.people.perf.pms_enums import AppealDecision, AppealStatus


class TestAppraisalAppealInstantiation:
    """Tests for model instantiation with required fields."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        appraisal_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        filed_date = date(2026, 3, 1)

        appeal = AppraisalAppeal(
            organization_id=org_id,
            appraisal_id=appraisal_id,
            employee_id=employee_id,
            filed_date=filed_date,
            reason="Manager rating was inconsistent with KPI scores.",
        )

        assert appeal.organization_id == org_id
        assert appeal.appraisal_id == appraisal_id
        assert appeal.employee_id == employee_id
        assert appeal.filed_date == filed_date
        assert appeal.reason == "Manager rating was inconsistent with KPI scores."

    def test_repr(self):
        """Model has a meaningful __repr__."""
        appeal_id = uuid.uuid4()
        appeal = AppraisalAppeal(appeal_id=appeal_id)
        assert str(appeal_id) in repr(appeal)


class TestAppraisalAppealDefaults:
    """Tests for default field values."""

    def test_default_status_is_filed(self):
        """Status column has FILED as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(AppraisalAppeal)
        col = mapper.columns["status"]
        assert col.default is not None
        assert col.default.arg == AppealStatus.FILED

    def test_appeal_id_column_has_uuid_default(self):
        """appeal_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(AppraisalAppeal)
        col = mapper.columns["appeal_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_mediation_resolved_defaults_false(self):
        """mediation_resolved column defaults to False."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(AppraisalAppeal)
        col = mapper.columns["mediation_resolved"]
        assert col.default is not None
        assert col.default.arg is False

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None on a freshly created instance."""
        appeal = AppraisalAppeal()

        assert appeal.requested_outcome is None
        assert appeal.mediator_id is None
        assert appeal.mediation_date is None
        assert appeal.mediation_outcome is None
        assert appeal.committee_referral_date is None
        assert appeal.committee_hearing_date is None
        assert appeal.committee_decision is None
        assert appeal.committee_notes is None
        assert appeal.adjusted_rating is None
        assert appeal.resolution_date is None
        assert appeal.resolution_notes is None
        assert appeal.communicated_date is None
        assert appeal.updated_at is None


class TestAppraisalAppealTableConfig:
    """Tests for SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'appraisal_appeal'."""
        assert AppraisalAppeal.__tablename__ == "appraisal_appeal"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = AppraisalAppeal.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_indexes_exist(self):
        """Required indexes are declared."""
        from sqlalchemy import Index

        table_args = AppraisalAppeal.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_appeal_appraisal" in index_names
        assert "idx_appeal_org_status" in index_names


class TestAppraisalAppealFields:
    """Tests for individual field properties."""

    def test_status_accepts_all_appeal_status_values(self):
        """status accepts all AppealStatus enum values."""
        for status in AppealStatus:
            appeal = AppraisalAppeal(status=status)
            assert appeal.status == status

    def test_committee_decision_accepts_all_appeal_decision_values(self):
        """committee_decision accepts all AppealDecision enum values."""
        for decision in AppealDecision:
            appeal = AppraisalAppeal(committee_decision=decision)
            assert appeal.committee_decision == decision

    def test_reason_accepts_multiline_text(self):
        """reason field accepts multiline text."""
        text = "Line 1\nLine 2\nLine 3"
        appeal = AppraisalAppeal(reason=text)
        assert appeal.reason == text

    def test_requested_outcome_accepts_text(self):
        """requested_outcome accepts text."""
        appeal = AppraisalAppeal(requested_outcome="Upgrade rating from 3 to 4.")
        assert appeal.requested_outcome == "Upgrade rating from 3 to 4."

    def test_adjusted_rating_accepts_integer(self):
        """adjusted_rating accepts an integer value."""
        appeal = AppraisalAppeal(adjusted_rating=4)
        assert appeal.adjusted_rating == 4

    def test_mediation_resolved_can_be_set_true(self):
        """mediation_resolved can be set to True."""
        appeal = AppraisalAppeal(mediation_resolved=True)
        assert appeal.mediation_resolved is True

    def test_filed_date_accepts_date(self):
        """filed_date accepts a date value."""
        d = date(2026, 3, 15)
        appeal = AppraisalAppeal(filed_date=d)
        assert appeal.filed_date == d

    def test_resolution_date_accepts_date(self):
        """resolution_date accepts a date value."""
        d = date(2026, 4, 10)
        appeal = AppraisalAppeal(resolution_date=d)
        assert appeal.resolution_date == d

    def test_mediator_id_accepts_uuid(self):
        """mediator_id accepts a UUID."""
        mediator_id = uuid.uuid4()
        appeal = AppraisalAppeal(mediator_id=mediator_id)
        assert appeal.mediator_id == mediator_id

    def test_committee_notes_accepts_text(self):
        """committee_notes accepts text."""
        notes = "Reviewed by committee on 2026-04-01."
        appeal = AppraisalAppeal(committee_notes=notes)
        assert appeal.committee_notes == notes

    def test_communicated_date_accepts_date(self):
        """communicated_date accepts a date value."""
        d = date(2026, 4, 15)
        appeal = AppraisalAppeal(communicated_date=d)
        assert appeal.communicated_date == d


class TestAppraisalAppealRelationships:
    """Tests for relationship declarations on the model."""

    def test_appraisal_relationship_declared(self):
        """'appraisal' relationship is declared."""
        assert hasattr(AppraisalAppeal, "appraisal")

    def test_employee_relationship_declared(self):
        """'employee' relationship is declared."""
        assert hasattr(AppraisalAppeal, "employee")

    def test_mediator_relationship_declared(self):
        """'mediator' relationship is declared."""
        assert hasattr(AppraisalAppeal, "mediator")


class TestAppraisalAppealInheritance:
    """Tests for proper base class inheritance."""

    def test_inherits_audit_mixin(self):
        """AppraisalAppeal inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(AppraisalAppeal(), AuditMixin)

    def test_audit_mixin_fields_present(self):
        """AuditMixin fields (created_by_id, updated_by_id) are present."""
        appeal = AppraisalAppeal()
        assert hasattr(appeal, "created_by_id")
        assert hasattr(appeal, "updated_by_id")

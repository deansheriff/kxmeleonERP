"""
Test suite for MonthlyReview model.

Verifies model instantiation, default values, field definitions,
table configuration, and relationship declarations.
"""

import uuid
from datetime import date

from app.models.people.perf.monthly_review import MonthlyReview
from app.models.people.perf.performance_contract import (
    PerformanceContract,  # noqa: F401 — registers mapper
)
from app.models.people.perf.pms_enums import MonthlyReviewStatus


class TestMonthlyReviewInstantiation:
    """Tests for model instantiation with required fields."""

    def test_instantiate_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        org_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        reviewer_id = uuid.uuid4()
        contract_id = uuid.uuid4()
        review_month = date(2026, 3, 1)

        review = MonthlyReview(
            organization_id=org_id,
            employee_id=employee_id,
            reviewer_id=reviewer_id,
            contract_id=contract_id,
            review_month=review_month,
        )

        assert review.organization_id == org_id
        assert review.employee_id == employee_id
        assert review.reviewer_id == reviewer_id
        assert review.contract_id == contract_id
        assert review.review_month == review_month

    def test_repr(self):
        """Model has a meaningful __repr__."""
        review = MonthlyReview(review_month=date(2026, 3, 1))
        r = repr(review)
        assert "MonthlyReview" in r
        assert "2026-03-01" in r


class TestMonthlyReviewDefaults:
    """Tests for default field values."""

    def test_default_status_is_draft(self):
        """Status column has DRAFT as its Python-level default."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(MonthlyReview)
        col = mapper.columns["status"]
        assert col.default is not None
        assert col.default.arg == MonthlyReviewStatus.DRAFT

    def test_review_id_column_has_uuid_default(self):
        """review_id column has a callable default (uuid generator)."""
        from sqlalchemy import inspect as sa_inspect

        mapper = sa_inspect(MonthlyReview)
        col = mapper.columns["review_id"]
        assert col.default is not None
        assert callable(col.default.arg)
        assert col.default.arg.__name__ == "uuid4"

    def test_nullable_fields_default_to_none(self):
        """All nullable fields default to None."""
        review = MonthlyReview()
        assert review.objective_progress is None
        assert review.challenges is None
        assert review.support_required is None
        assert review.reviewer_feedback is None
        assert review.agreed_actions is None
        assert review.employee_signed_date is None
        assert review.reviewer_signed_date is None
        assert review.updated_at is None


class TestMonthlyReviewTableConfig:
    """Tests for SQLAlchemy table configuration."""

    def test_table_name(self):
        """Table name is 'monthly_review'."""
        assert MonthlyReview.__tablename__ == "monthly_review"

    def test_schema(self):
        """Table is in the 'perf' schema."""
        table_args = MonthlyReview.__table_args__
        schema_dict = table_args[-1]
        assert isinstance(schema_dict, dict)
        assert schema_dict.get("schema") == "perf"

    def test_unique_constraint_exists(self):
        """UniqueConstraint on organization_id + employee_id + review_month exists."""
        from sqlalchemy import UniqueConstraint

        table_args = MonthlyReview.__table_args__
        constraints = [a for a in table_args if isinstance(a, UniqueConstraint)]
        assert len(constraints) == 1
        uc = constraints[0]
        assert uc.name == "uq_monthly_review"

    def test_indexes_exist(self):
        """All required indexes are declared."""
        from sqlalchemy import Index

        table_args = MonthlyReview.__table_args__
        indexes = [a for a in table_args if isinstance(a, Index)]
        index_names = {idx.name for idx in indexes}
        assert "idx_review_employee" in index_names
        assert "idx_review_month" in index_names


class TestMonthlyReviewFields:
    """Tests for individual field properties."""

    def test_status_accepts_all_enum_values(self):
        """status accepts all MonthlyReviewStatus enum values."""
        for s in MonthlyReviewStatus:
            review = MonthlyReview(status=s)
            assert review.status == s

    def test_objective_progress_accepts_dict(self):
        """objective_progress accepts a JSON-serialisable dict."""
        data = {"kra_1": {"target": 100, "achieved": 75}}
        review = MonthlyReview(objective_progress=data)
        assert review.objective_progress == data

    def test_objective_progress_accepts_list(self):
        """objective_progress accepts a JSON-serialisable list."""
        data = [{"kra": "Revenue", "progress": 80}]
        review = MonthlyReview(objective_progress=data)
        assert review.objective_progress == data

    def test_challenges_accepts_text(self):
        """challenges accepts multiline text."""
        text = "Challenge 1: Lack of resources\nChallenge 2: Delayed approvals"
        review = MonthlyReview(challenges=text)
        assert review.challenges == text

    def test_support_required_accepts_text(self):
        """support_required accepts text."""
        review = MonthlyReview(support_required="Need additional training")
        assert review.support_required == "Need additional training"

    def test_reviewer_feedback_accepts_text(self):
        """reviewer_feedback accepts text."""
        review = MonthlyReview(reviewer_feedback="Good progress on KPIs")
        assert review.reviewer_feedback == "Good progress on KPIs"

    def test_agreed_actions_accepts_text(self):
        """agreed_actions accepts text."""
        review = MonthlyReview(agreed_actions="Complete report by end of month")
        assert review.agreed_actions == "Complete report by end of month"

    def test_employee_signed_date_accepts_date(self):
        """employee_signed_date accepts a date value."""
        d = date(2026, 3, 15)
        review = MonthlyReview(employee_signed_date=d)
        assert review.employee_signed_date == d

    def test_reviewer_signed_date_accepts_date(self):
        """reviewer_signed_date accepts a date value."""
        d = date(2026, 3, 20)
        review = MonthlyReview(reviewer_signed_date=d)
        assert review.reviewer_signed_date == d

    def test_review_month_accepts_date(self):
        """review_month accepts a date (typically first of month)."""
        review = MonthlyReview(review_month=date(2026, 2, 1))
        assert review.review_month == date(2026, 2, 1)


class TestMonthlyReviewRelationships:
    """Tests for relationship declarations on the model."""

    def test_employee_relationship_declared(self):
        """'employee' relationship is declared."""
        assert hasattr(MonthlyReview, "employee")

    def test_reviewer_relationship_declared(self):
        """'reviewer' relationship is declared."""
        assert hasattr(MonthlyReview, "reviewer")

    def test_contract_relationship_declared(self):
        """'contract' relationship is declared."""
        assert hasattr(MonthlyReview, "contract")


class TestMonthlyReviewInheritance:
    """Tests for proper base class inheritance."""

    def test_inherits_audit_mixin(self):
        """MonthlyReview inherits from AuditMixin."""
        from app.models.people.base import AuditMixin

        assert isinstance(MonthlyReview(), AuditMixin)

    def test_audit_mixin_fields_present(self):
        """AuditMixin fields (created_by_id, updated_by_id) are present."""
        review = MonthlyReview()
        assert hasattr(review, "created_by_id")
        assert hasattr(review, "updated_by_id")

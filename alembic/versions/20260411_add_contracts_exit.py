"""Add employment contract, exit interview, and clearance item tables

Revision ID: 20260411_add_contracts_exit
Revises: 20260411_add_survey_succession, 20260411_merge_all_heads
Create Date: 2026-04-11 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.alembic_utils import ensure_enum

# revision identifiers, used by Alembic.
revision = "20260411_add_contracts_exit"
down_revision = ("20260411_add_survey_succession", "20260411_merge_all_heads")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # Enum types (idempotent via ensure_enum)
    # ------------------------------------------------------------------
    hr_contract_type = ensure_enum(
        bind,
        "hr_contract_type",
        "PERMANENT",
        "FIXED_TERM",
        "PROBATION",
        "INTERNSHIP",
        "CASUAL",
        "CONSULTANT",
    )
    hr_contract_status = ensure_enum(
        bind,
        "hr_contract_status",
        "DRAFT",
        "ACTIVE",
        "EXPIRING",
        "EXPIRED",
        "RENEWED",
        "TERMINATED",
    )
    hr_overall_experience = ensure_enum(
        bind,
        "hr_overall_experience",
        "EXCELLENT",
        "GOOD",
        "FAIR",
        "POOR",
    )
    hr_reason_for_leaving = ensure_enum(
        bind,
        "hr_reason_for_leaving",
        "BETTER_OPPORTUNITY",
        "COMPENSATION",
        "MANAGEMENT",
        "CULTURE",
        "PERSONAL",
        "RELOCATION",
        "CAREER_GROWTH",
        "WORK_LIFE_BALANCE",
        "OTHER",
    )
    hr_interview_status = ensure_enum(
        bind,
        "hr_interview_status",
        "PENDING",
        "SCHEDULED",
        "COMPLETED",
        "SKIPPED",
    )
    hr_clearance_category = ensure_enum(
        bind,
        "hr_clearance_category",
        "IT_ACCESS",
        "EQUIPMENT",
        "FINANCE",
        "HR_DOCUMENTS",
        "KNOWLEDGE_TRANSFER",
        "OTHER",
    )

    # ------------------------------------------------------------------
    # hr.employment_contract
    # ------------------------------------------------------------------
    if not _table_exists(bind, "employment_contract", schema="hr"):
        op.create_table(
            "employment_contract",
            sa.Column(
                "contract_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("core_org.organization.organization_id"),
                nullable=False,
            ),
            sa.Column(
                "employee_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee.employee_id"),
                nullable=False,
            ),
            sa.Column("contract_number", sa.String(30), nullable=False),
            sa.Column("contract_type", hr_contract_type, nullable=False),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=True),
            sa.Column("probation_end_date", sa.Date, nullable=True),
            sa.Column("terms", sa.Text, nullable=True),
            sa.Column("salary_amount", sa.Numeric(20, 6), nullable=True),
            sa.Column(
                "currency_code",
                sa.String(3),
                nullable=False,
                server_default="NGN",
            ),
            sa.Column(
                "notice_period_days",
                sa.Integer,
                nullable=False,
                server_default="30",
            ),
            sa.Column("working_hours_per_week", sa.Numeric(5, 2), nullable=True),
            sa.Column(
                "previous_contract_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employment_contract.contract_id"),
                nullable=True,
            ),
            sa.Column(
                "renewed_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employment_contract.contract_id"),
                nullable=True,
            ),
            sa.Column(
                "document_template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("automation.document_template.template_id"),
                nullable=True,
            ),
            sa.Column(
                "generated_document_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("automation.generated_document.document_id"),
                nullable=True,
            ),
            sa.Column(
                "status",
                hr_contract_status,
                nullable=False,
                server_default="DRAFT",
            ),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column(
                "created_by_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column(
                "updated_by_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "organization_id",
                "contract_number",
                name="uq_employment_contract_org_number",
            ),
            schema="hr",
        )
        op.create_index(
            "idx_contract_org_employee",
            "employment_contract",
            ["organization_id", "employee_id"],
            schema="hr",
        )
        op.create_index(
            "idx_contract_org_status",
            "employment_contract",
            ["organization_id", "status"],
            schema="hr",
        )
        op.create_index(
            "idx_contract_end_date",
            "employment_contract",
            ["end_date", "status"],
            schema="hr",
        )
        op.create_index(
            "ix_employment_contract_organization_id",
            "employment_contract",
            ["organization_id"],
            schema="hr",
        )

    # ------------------------------------------------------------------
    # hr.exit_interview
    # ------------------------------------------------------------------
    if not _table_exists(bind, "exit_interview", schema="hr"):
        op.create_table(
            "exit_interview",
            sa.Column(
                "interview_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("core_org.organization.organization_id"),
                nullable=False,
            ),
            sa.Column(
                "separation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee_separation.separation_id"),
                nullable=False,
            ),
            sa.Column(
                "employee_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee.employee_id"),
                nullable=False,
            ),
            sa.Column(
                "conducted_by_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee.employee_id"),
                nullable=True,
            ),
            sa.Column("interview_date", sa.Date, nullable=True),
            sa.Column(
                "overall_experience",
                hr_overall_experience,
                nullable=True,
            ),
            sa.Column(
                "reason_for_leaving",
                hr_reason_for_leaving,
                nullable=True,
            ),
            sa.Column("would_recommend", sa.Boolean, nullable=True),
            sa.Column("would_return", sa.Boolean, nullable=True),
            sa.Column("likes_about_company", sa.Text, nullable=True),
            sa.Column("dislikes_about_company", sa.Text, nullable=True),
            sa.Column("suggestions", sa.Text, nullable=True),
            sa.Column("management_feedback", sa.Text, nullable=True),
            sa.Column("additional_comments", sa.Text, nullable=True),
            sa.Column(
                "status",
                hr_interview_status,
                nullable=False,
                server_default="PENDING",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "separation_id",
                name="uq_exit_interview_separation",
            ),
            schema="hr",
        )
        op.create_index(
            "idx_exit_interview_org",
            "exit_interview",
            ["organization_id"],
            schema="hr",
        )
        op.create_index(
            "idx_exit_interview_employee",
            "exit_interview",
            ["organization_id", "employee_id"],
            schema="hr",
        )

    # ------------------------------------------------------------------
    # hr.clearance_item
    # ------------------------------------------------------------------
    if not _table_exists(bind, "clearance_item", schema="hr"):
        op.create_table(
            "clearance_item",
            sa.Column(
                "item_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("core_org.organization.organization_id"),
                nullable=False,
            ),
            sa.Column(
                "separation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee_separation.separation_id"),
                nullable=False,
            ),
            sa.Column("category", hr_clearance_category, nullable=False),
            sa.Column("description", sa.String(300), nullable=False),
            sa.Column(
                "assigned_to_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("hr.employee.employee_id"),
                nullable=True,
            ),
            sa.Column(
                "is_cleared",
                sa.Boolean,
                nullable=False,
                server_default="false",
            ),
            sa.Column(
                "cleared_by_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column(
                "cleared_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            sa.Column("notes", sa.Text, nullable=True),
            sa.Column(
                "sort_order",
                sa.Integer,
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            schema="hr",
        )
        op.create_index(
            "idx_clearance_org_separation",
            "clearance_item",
            ["organization_id", "separation_id"],
            schema="hr",
        )
        op.create_index(
            "idx_clearance_is_cleared",
            "clearance_item",
            ["separation_id", "is_cleared"],
            schema="hr",
        )


def downgrade() -> None:
    op.drop_table("clearance_item", schema="hr")
    op.drop_table("exit_interview", schema="hr")
    op.drop_table("employment_contract", schema="hr")

    bind = op.get_bind()
    for name in (
        "hr_clearance_category",
        "hr_interview_status",
        "hr_reason_for_leaving",
        "hr_overall_experience",
        "hr_contract_status",
        "hr_contract_type",
    ):
        postgresql.ENUM(name=name, create_type=False).drop(bind, checkfirst=True)


def _table_exists(bind: sa.engine.Connection, table: str, schema: str) -> bool:
    """Check if a table exists in the given schema."""
    result = bind.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = :schema AND table_name = :table"
            ")"
        ),
        {"schema": schema, "table": table},
    )
    return bool(result.scalar())

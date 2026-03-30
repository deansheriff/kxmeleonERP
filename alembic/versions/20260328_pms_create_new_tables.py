"""PMS OHCSF: create new performance management tables.

Revision ID: 20260328_pms_create_new_tables
Revises: 20260328_pms_extend_existing_models
Create Date: 2026-03-28

Creates 9 new tables in the perf schema:
  1. strategic_objective
  2. performance_contract
  3. monthly_review
  4. performance_improvement_plan
  5. appraisal_appeal
  6. institutional_performance
  7. institutional_criteria_template
  8. competency_assessment
  9. appraisal_outcome_action

Also adds FK: perf.kpi.institutional_objective_id → perf.strategic_objective.objective_id

NOTE: FKs to core_org.organization, hr.*, and perf.* reference tables are declared at
the ORM layer only. The DB does not enforce them via pg_constraint because the referenced
tables were created without formal PK constraints (consistent with the existing schema).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.alembic_utils import ensure_enum

revision = "20260328_pms_create_new_tables"
down_revision = "20260328_pms_extend_existing_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # Ensure all required enum types exist
    # ------------------------------------------------------------------
    ensure_enum(
        bind,
        "contract_type",
        "MINISTERIAL",
        "DEPARTMENTAL",
        "INDIVIDUAL",
        schema="perf",
    )
    ensure_enum(
        bind,
        "contract_status",
        "DRAFT",
        "PENDING_SIGNATURE",
        "ACTIVE",
        "AMENDED",
        "COMPLETED",
        "CANCELLED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "monthly_review_status",
        "DRAFT",
        "SUBMITTED",
        "ACKNOWLEDGED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "pip_status",
        "DRAFT",
        "ACTIVE",
        "UNDER_REVIEW",
        "IMPROVED",
        "EXTENDED",
        "ESCALATED",
        "CLOSED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "pip_cause_category",
        "CLARITY",
        "SKILLS",
        "COMMITMENT",
        "HEALTH",
        "PERSONAL",
        schema="perf",
    )
    ensure_enum(
        bind,
        "pip_outcome",
        "SATISFACTORY",
        "UNSATISFACTORY",
        schema="perf",
    )
    ensure_enum(
        bind,
        "appeal_status",
        "FILED",
        "UNDER_MEDIATION",
        "REFERRED_TO_COMMITTEE",
        "RESOLVED",
        "DISMISSED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "appeal_decision",
        "UPHELD",
        "PARTIALLY_UPHELD",
        "DISMISSED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "institution_type",
        "MINISTRY",
        "REGULATORY",
        "GENERAL_SERVICES",
        "INFRASTRUCTURE",
        "SECURITY",
        "GOVT_COMPANY",
        schema="perf",
    )
    ensure_enum(
        bind,
        "institutional_perf_status",
        "DRAFT",
        "UNDER_REVIEW",
        "APPRAISED",
        "RECONCILED",
        "COMPLETED",
        schema="perf",
    )
    ensure_enum(
        bind,
        "outcome_action_type",
        "REWARD",
        "PIP",
        "TRAINING",
        "TRANSFER",
        "PROMOTION",
        "DEMOTION",
        "REMOVAL",
        "COUNSELING",
        schema="perf",
    )
    ensure_enum(
        bind,
        "outcome_action_status",
        "PENDING",
        "COMPLETED",
        "CANCELLED",
        schema="perf",
    )

    # ------------------------------------------------------------------
    # 1. perf.strategic_objective  (created FIRST — other tables FK to it)
    # ------------------------------------------------------------------
    if not inspector.has_table("strategic_objective", schema="perf"):
        op.create_table(
            "strategic_objective",
            sa.Column(
                "objective_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "parent_objective_id", postgresql.UUID(as_uuid=True), nullable=True
            ),
            sa.Column("objective_code", sa.String(30), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source_document", sa.String(200), nullable=True),
            sa.Column("target_description", sa.Text(), nullable=True),
            sa.Column("weight", sa.Numeric(5, 2), nullable=True),
            sa.Column(
                "sequence", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints — PK and unique only (no FKs: referenced tables have no formal PK constraints)
            sa.PrimaryKeyConstraint("objective_id"),
            sa.UniqueConstraint(
                "organization_id", "objective_code", name="uq_strategic_obj_code"
            ),
            schema="perf",
        )
        op.create_index(
            "idx_strat_obj_cycle", "strategic_objective", ["cycle_id"], schema="perf"
        )
        op.create_index(
            "idx_strat_obj_dept",
            "strategic_objective",
            ["organization_id", "department_id"],
            schema="perf",
        )
        op.create_index(
            "idx_strat_obj_org",
            "strategic_objective",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 2. perf.performance_contract
    # ------------------------------------------------------------------
    if not inspector.has_table("performance_contract", schema="perf"):
        op.create_table(
            "performance_contract",
            sa.Column(
                "contract_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("contract_code", sa.String(30), nullable=False),
            sa.Column(
                "contract_type",
                postgresql.ENUM(
                    "MINISTERIAL",
                    "DEPARTMENTAL",
                    "INDIVIDUAL",
                    name="contract_type",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "DRAFT",
                    "PENDING_SIGNATURE",
                    "ACTIVE",
                    "AMENDED",
                    "COMPLETED",
                    "CANCELLED",
                    name="contract_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("objectives", sa.JSON(), nullable=False),
            sa.Column("competency_ids", sa.JSON(), nullable=True),
            sa.Column("development_plan", sa.Text(), nullable=True),
            sa.Column("employee_signed_date", sa.Date(), nullable=True),
            sa.Column("supervisor_signed_date", sa.Date(), nullable=True),
            sa.Column("countersigner_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("countersigner_date", sa.Date(), nullable=True),
            sa.Column("amended_from_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("amendment_reason", sa.Text(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("contract_id"),
            sa.UniqueConstraint(
                "organization_id", "contract_code", name="uq_perf_contract_code"
            ),
            schema="perf",
        )
        op.create_index(
            "idx_contract_employee",
            "performance_contract",
            ["employee_id"],
            schema="perf",
        )
        op.create_index(
            "idx_contract_cycle", "performance_contract", ["cycle_id"], schema="perf"
        )
        op.create_index(
            "idx_contract_org_status",
            "performance_contract",
            ["organization_id", "status"],
            schema="perf",
        )
        op.create_index(
            "idx_contract_org",
            "performance_contract",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 3. perf.monthly_review
    # ------------------------------------------------------------------
    if not inspector.has_table("monthly_review", schema="perf"):
        op.create_table(
            "monthly_review",
            sa.Column(
                "review_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("review_month", sa.Date(), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "DRAFT",
                    "SUBMITTED",
                    "ACKNOWLEDGED",
                    name="monthly_review_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("objective_progress", sa.JSON(), nullable=True),
            sa.Column("challenges", sa.Text(), nullable=True),
            sa.Column("support_required", sa.Text(), nullable=True),
            sa.Column("reviewer_feedback", sa.Text(), nullable=True),
            sa.Column("agreed_actions", sa.Text(), nullable=True),
            sa.Column("employee_signed_date", sa.Date(), nullable=True),
            sa.Column("reviewer_signed_date", sa.Date(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("review_id"),
            sa.UniqueConstraint(
                "organization_id",
                "employee_id",
                "review_month",
                name="uq_monthly_review",
            ),
            schema="perf",
        )
        op.create_index(
            "idx_review_employee", "monthly_review", ["employee_id"], schema="perf"
        )
        op.create_index(
            "idx_review_month",
            "monthly_review",
            ["organization_id", "review_month"],
            schema="perf",
        )
        op.create_index(
            "idx_review_org", "monthly_review", ["organization_id"], schema="perf"
        )

    # ------------------------------------------------------------------
    # 4. perf.performance_improvement_plan
    # ------------------------------------------------------------------
    if not inspector.has_table("performance_improvement_plan", schema="perf"):
        op.create_table(
            "performance_improvement_plan",
            sa.Column(
                "pip_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("hr_officer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("appraisal_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("pip_code", sa.String(30), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "DRAFT",
                    "ACTIVE",
                    "UNDER_REVIEW",
                    "IMPROVED",
                    "EXTENDED",
                    "ESCALATED",
                    "CLOSED",
                    name="pip_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column(
                "cause_category",
                postgresql.ENUM(
                    "CLARITY",
                    "SKILLS",
                    "COMMITMENT",
                    "HEALTH",
                    "PERSONAL",
                    name="pip_cause_category",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("improvement_areas", sa.JSON(), nullable=False),
            sa.Column("support_measures", sa.Text(), nullable=True),
            sa.Column("review_intervals", sa.JSON(), nullable=True),
            sa.Column(
                "extension_granted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("extension_end_date", sa.Date(), nullable=True),
            sa.Column("extension_reason", sa.Text(), nullable=True),
            sa.Column(
                "outcome",
                postgresql.ENUM(
                    "SATISFACTORY",
                    "UNSATISFACTORY",
                    name="pip_outcome",
                    schema="perf",
                    create_type=False,
                ),
                nullable=True,
            ),
            sa.Column("outcome_date", sa.Date(), nullable=True),
            sa.Column("outcome_notes", sa.Text(), nullable=True),
            sa.Column(
                "completion_letter_issued",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("escalation_action", sa.String(50), nullable=True),
            sa.Column("committee_referral_date", sa.Date(), nullable=True),
            sa.Column("committee_decision", sa.Text(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("pip_id"),
            sa.UniqueConstraint("organization_id", "pip_code", name="uq_pip_code"),
            schema="perf",
        )
        op.create_index(
            "idx_pip_employee",
            "performance_improvement_plan",
            ["employee_id"],
            schema="perf",
        )
        op.create_index(
            "idx_pip_org_status",
            "performance_improvement_plan",
            ["organization_id", "status"],
            schema="perf",
        )
        op.create_index(
            "idx_pip_org",
            "performance_improvement_plan",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 5. perf.appraisal_appeal
    # ------------------------------------------------------------------
    if not inspector.has_table("appraisal_appeal", schema="perf"):
        op.create_table(
            "appraisal_appeal",
            sa.Column(
                "appeal_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("appraisal_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "FILED",
                    "UNDER_MEDIATION",
                    "REFERRED_TO_COMMITTEE",
                    "RESOLVED",
                    "DISMISSED",
                    name="appeal_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("filed_date", sa.Date(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("requested_outcome", sa.Text(), nullable=True),
            sa.Column("mediator_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("mediation_date", sa.Date(), nullable=True),
            sa.Column("mediation_outcome", sa.Text(), nullable=True),
            sa.Column(
                "mediation_resolved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("committee_referral_date", sa.Date(), nullable=True),
            sa.Column("committee_hearing_date", sa.Date(), nullable=True),
            sa.Column(
                "committee_decision",
                postgresql.ENUM(
                    "UPHELD",
                    "PARTIALLY_UPHELD",
                    "DISMISSED",
                    name="appeal_decision",
                    schema="perf",
                    create_type=False,
                ),
                nullable=True,
            ),
            sa.Column("committee_notes", sa.Text(), nullable=True),
            sa.Column("adjusted_rating", sa.Integer(), nullable=True),
            sa.Column("resolution_date", sa.Date(), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("communicated_date", sa.Date(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("appeal_id"),
            schema="perf",
        )
        op.create_index(
            "idx_appeal_appraisal", "appraisal_appeal", ["appraisal_id"], schema="perf"
        )
        op.create_index(
            "idx_appeal_org_status",
            "appraisal_appeal",
            ["organization_id", "status"],
            schema="perf",
        )
        op.create_index(
            "idx_appeal_org", "appraisal_appeal", ["organization_id"], schema="perf"
        )

    # ------------------------------------------------------------------
    # 6. perf.institutional_performance
    # ------------------------------------------------------------------
    if not inspector.has_table("institutional_performance", schema="perf"):
        op.create_table(
            "institutional_performance",
            sa.Column(
                "inst_perf_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "institution_type",
                postgresql.ENUM(
                    "MINISTRY",
                    "REGULATORY",
                    "GENERAL_SERVICES",
                    "INFRASTRUCTURE",
                    "SECURITY",
                    "GOVT_COMPANY",
                    name="institution_type",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "DRAFT",
                    "UNDER_REVIEW",
                    "APPRAISED",
                    "RECONCILED",
                    "COMPLETED",
                    name="institutional_perf_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("criteria_scores", sa.JSON(), nullable=True),
            sa.Column("composite_score", sa.Numeric(5, 2), nullable=True),
            sa.Column("rating_label", sa.String(50), nullable=True),
            sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("review_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column(
                "is_reconciled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("pre_reconciliation_composite", sa.Numeric(5, 2), nullable=True),
            sa.Column("reconciled_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("reconciliation_date", sa.Date(), nullable=True),
            sa.Column("reconciliation_notes", sa.Text(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("inst_perf_id"),
            schema="perf",
        )
        op.create_index(
            "idx_inst_perf_cycle",
            "institutional_performance",
            ["cycle_id"],
            schema="perf",
        )
        op.create_index(
            "idx_inst_perf_dept",
            "institutional_performance",
            ["organization_id", "department_id"],
            schema="perf",
        )
        op.create_index(
            "idx_inst_perf_org",
            "institutional_performance",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 7. perf.institutional_criteria_template  (NO AuditMixin)
    # ------------------------------------------------------------------
    if not inspector.has_table("institutional_criteria_template", schema="perf"):
        op.create_table(
            "institutional_criteria_template",
            sa.Column(
                "template_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "institution_type",
                postgresql.ENUM(
                    "MINISTRY",
                    "REGULATORY",
                    "GENERAL_SERVICES",
                    "INFRASTRUCTURE",
                    "SECURITY",
                    "GOVT_COMPANY",
                    name="institution_type",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("criteria_name", sa.String(100), nullable=False),
            sa.Column("default_weight", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            # Timestamps only (no AuditMixin)
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            # Constraints
            sa.PrimaryKeyConstraint("template_id"),
            schema="perf",
        )
        op.create_index(
            "idx_criteria_tmpl_type",
            "institutional_criteria_template",
            ["organization_id", "institution_type"],
            schema="perf",
        )
        op.create_index(
            "idx_criteria_tmpl_org",
            "institutional_criteria_template",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 8. perf.competency_assessment  (NO AuditMixin — timestamps only)
    # ------------------------------------------------------------------
    if not inspector.has_table("competency_assessment", schema="perf"):
        op.create_table(
            "competency_assessment",
            sa.Column(
                "assessment_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("appraisal_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "is_priority",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "is_development_focus",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("target_proficiency", sa.Integer(), nullable=True),
            sa.Column("self_rating", sa.Integer(), nullable=True),
            sa.Column("manager_rating", sa.Integer(), nullable=True),
            sa.Column("final_rating", sa.Integer(), nullable=True),
            sa.Column("evidence", sa.Text(), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("assessment_id"),
            schema="perf",
        )
        op.create_index(
            "idx_comp_assess_appraisal",
            "competency_assessment",
            ["appraisal_id"],
            schema="perf",
        )
        op.create_index(
            "idx_comp_assess_org",
            "competency_assessment",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 9. perf.appraisal_outcome_action
    # ------------------------------------------------------------------
    if not inspector.has_table("appraisal_outcome_action", schema="perf"):
        op.create_table(
            "appraisal_outcome_action",
            sa.Column(
                "action_id",
                postgresql.UUID(as_uuid=True),
                server_default=sa.text("gen_random_uuid()"),
                nullable=False,
            ),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("appraisal_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "action_type",
                postgresql.ENUM(
                    "REWARD",
                    "PIP",
                    "TRAINING",
                    "TRANSFER",
                    "PROMOTION",
                    "DEMOTION",
                    "REMOVAL",
                    "COUNSELING",
                    name="outcome_action_type",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("actioned_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("actioned_date", sa.Date(), nullable=True),
            sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("reference_type", sa.String(50), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(
                    "PENDING",
                    "COMPLETED",
                    "CANCELLED",
                    name="outcome_action_status",
                    schema="perf",
                    create_type=False,
                ),
                nullable=False,
            ),
            sa.Column("notes", sa.Text(), nullable=True),
            # AuditMixin
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            # Constraints
            sa.PrimaryKeyConstraint("action_id"),
            schema="perf",
        )
        op.create_index(
            "idx_outcome_appraisal",
            "appraisal_outcome_action",
            ["appraisal_id"],
            schema="perf",
        )
        op.create_index(
            "idx_outcome_org",
            "appraisal_outcome_action",
            ["organization_id"],
            schema="perf",
        )

    # ------------------------------------------------------------------
    # 10. FK: perf.kpi.institutional_objective_id → perf.strategic_objective
    #     Only create if strategic_objective now has a PK constraint
    # ------------------------------------------------------------------
    if inspector.has_table("kpi", schema="perf") and inspector.has_table(
        "strategic_objective", schema="perf"
    ):
        kpi_cols = {c["name"] for c in inspector.get_columns("kpi", schema="perf")}
        if "institutional_objective_id" in kpi_cols:
            existing_fks = {
                fk["name"] for fk in inspector.get_foreign_keys("kpi", schema="perf")
            }
            if "fk_kpi_institutional_objective" not in existing_fks:
                # Check if strategic_objective has a PK before adding FK
                so_pk = inspector.get_pk_constraint(
                    "strategic_objective", schema="perf"
                )
                if so_pk and so_pk.get("constrained_columns"):
                    op.create_foreign_key(
                        "fk_kpi_institutional_objective",
                        "kpi",
                        "strategic_objective",
                        ["institutional_objective_id"],
                        ["objective_id"],
                        source_schema="perf",
                        referent_schema="perf",
                    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop FK from kpi first (if it was created)
    if inspector.has_table("kpi", schema="perf"):
        fks = {fk["name"] for fk in inspector.get_foreign_keys("kpi", schema="perf")}
        if "fk_kpi_institutional_objective" in fks:
            op.drop_constraint(
                "fk_kpi_institutional_objective",
                "kpi",
                schema="perf",
                type_="foreignkey",
            )

    # Drop tables in reverse dependency order
    tables_to_drop = [
        "appraisal_outcome_action",
        "competency_assessment",
        "institutional_criteria_template",
        "institutional_performance",
        "appraisal_appeal",
        "performance_improvement_plan",
        "monthly_review",
        "performance_contract",
        "strategic_objective",
    ]
    for table in tables_to_drop:
        if inspector.has_table(table, schema="perf"):
            op.drop_table(table, schema="perf")

    # Drop enum types (in reverse order)
    enum_names = [
        "outcome_action_status",
        "outcome_action_type",
        "institutional_perf_status",
        "institution_type",
        "appeal_decision",
        "appeal_status",
        "pip_outcome",
        "pip_cause_category",
        "pip_status",
        "monthly_review_status",
        "contract_status",
        "contract_type",
    ]
    for enum_name in enum_names:
        op.execute(f"DROP TYPE IF EXISTS perf.{enum_name}")

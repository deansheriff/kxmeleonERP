"""PMS OHCSF: extend existing tables with new columns.

Revision ID: 20260328_pms_extend_existing_models
Revises: 20260327_add_employee_nysc_dates
Create Date: 2026-03-28

Extends:
- core_org.organization: pms_ohcsf_enabled
- perf.appraisal_cycle: cycle_type, parent_cycle_id, quarter
- perf.appraisal: 26 OHCSF fields
- perf.appraisal_kra_score: 11 OHCSF fields
- perf.kpi: institutional_objective_id
- perf.appraisal_status enum: PENDING_COUNTERSIGN, COUNTERSIGNED, PENDING_COMMITTEE
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260328_pms_extend_existing_models"
down_revision = "20260327_add_employee_nysc_dates"
branch_labels = None
depends_on = None


def _add_column_if_missing(
    inspector, table: str, schema: str, col_name: str, col_def
) -> None:
    """Add a column only if it does not already exist."""
    existing = {c["name"] for c in inspector.get_columns(table, schema=schema)}
    if col_name not in existing:
        op.add_column(table, col_def, schema=schema)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # 1. core_org.organization — pms_ohcsf_enabled
    # ------------------------------------------------------------------
    if inspector.has_table("organization", schema="core_org"):
        _add_column_if_missing(
            inspector,
            "organization",
            "core_org",
            "pms_ohcsf_enabled",
            sa.Column(
                "pms_ohcsf_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # ------------------------------------------------------------------
    # 2. perf.appraisal_cycle — cycle_type, parent_cycle_id, quarter
    # ------------------------------------------------------------------
    if inspector.has_table("appraisal_cycle", schema="perf"):
        _add_column_if_missing(
            inspector,
            "appraisal_cycle",
            "perf",
            "cycle_type",
            sa.Column(
                "cycle_type",
                sa.String(20),
                nullable=False,
                server_default=sa.text("'ANNUAL'"),
            ),
        )
        _add_column_if_missing(
            inspector,
            "appraisal_cycle",
            "perf",
            "parent_cycle_id",
            sa.Column(
                "parent_cycle_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )
        _add_column_if_missing(
            inspector,
            "appraisal_cycle",
            "perf",
            "quarter",
            sa.Column("quarter", sa.Integer(), nullable=True),
        )

        # FK: appraisal_cycle → self (parent_cycle_id)
        existing_fks = {
            fk["name"]
            for fk in inspector.get_foreign_keys("appraisal_cycle", schema="perf")
        }
        if "fk_cycle_parent" not in existing_fks:
            cycle_cols = {
                c["name"]
                for c in inspector.get_columns("appraisal_cycle", schema="perf")
            }
            if "parent_cycle_id" in cycle_cols:
                op.create_foreign_key(
                    "fk_cycle_parent",
                    "appraisal_cycle",
                    "appraisal_cycle",
                    ["parent_cycle_id"],
                    ["cycle_id"],
                    source_schema="perf",
                    referent_schema="perf",
                )

    # ------------------------------------------------------------------
    # 3. perf.appraisal_status enum — add missing values
    # ------------------------------------------------------------------
    # Use DO $$ ... $$ to add values idempotently
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'PENDING_COUNTERSIGN'
                  AND enumtypid = (
                      SELECT oid FROM pg_type
                      WHERE typname = 'appraisal_status'
                        AND typnamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = 'perf'
                        )
                  )
            ) THEN
                ALTER TYPE perf.appraisal_status ADD VALUE 'PENDING_COUNTERSIGN';
            END IF;
        END$$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'COUNTERSIGNED'
                  AND enumtypid = (
                      SELECT oid FROM pg_type
                      WHERE typname = 'appraisal_status'
                        AND typnamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = 'perf'
                        )
                  )
            ) THEN
                ALTER TYPE perf.appraisal_status ADD VALUE 'COUNTERSIGNED';
            END IF;
        END$$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'PENDING_COMMITTEE'
                  AND enumtypid = (
                      SELECT oid FROM pg_type
                      WHERE typname = 'appraisal_status'
                        AND typnamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = 'perf'
                        )
                  )
            ) THEN
                ALTER TYPE perf.appraisal_status ADD VALUE 'PENDING_COMMITTEE';
            END IF;
        END$$;
    """)

    # ------------------------------------------------------------------
    # 4. perf.appraisal — 26 OHCSF fields
    # ------------------------------------------------------------------
    if inspector.has_table("appraisal", schema="perf"):
        appraisal_new_cols = [
            (
                "counter_signer_id",
                sa.Column(
                    "counter_signer_id", postgresql.UUID(as_uuid=True), nullable=True
                ),
            ),
            (
                "counter_signer_date",
                sa.Column("counter_signer_date", sa.Date(), nullable=True),
            ),
            (
                "counter_signer_comments",
                sa.Column("counter_signer_comments", sa.Text(), nullable=True),
            ),
            (
                "committee_review_date",
                sa.Column("committee_review_date", sa.Date(), nullable=True),
            ),
            (
                "committee_decision",
                sa.Column("committee_decision", sa.String(50), nullable=True),
            ),
            ("committee_notes", sa.Column("committee_notes", sa.Text(), nullable=True)),
            (
                "is_quarterly",
                sa.Column(
                    "is_quarterly",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "quarterly_rating",
                sa.Column("quarterly_rating", sa.Numeric(5, 2), nullable=True),
            ),
            (
                "process_self_rating",
                sa.Column("process_self_rating", sa.Integer(), nullable=True),
            ),
            (
                "process_manager_rating",
                sa.Column("process_manager_rating", sa.Integer(), nullable=True),
            ),
            (
                "process_final_rating",
                sa.Column("process_final_rating", sa.Integer(), nullable=True),
            ),
            (
                "process_comments",
                sa.Column("process_comments", sa.Text(), nullable=True),
            ),
            (
                "objective_weighted_score",
                sa.Column("objective_weighted_score", sa.Numeric(5, 2), nullable=True),
            ),
            (
                "competency_weighted_score",
                sa.Column("competency_weighted_score", sa.Numeric(5, 2), nullable=True),
            ),
            (
                "process_weighted_score",
                sa.Column("process_weighted_score", sa.Numeric(5, 2), nullable=True),
            ),
            (
                "is_prior_year_carryover",
                sa.Column(
                    "is_prior_year_carryover",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "carryover_source_id",
                sa.Column(
                    "carryover_source_id", postgresql.UUID(as_uuid=True), nullable=True
                ),
            ),
            (
                "absence_months",
                sa.Column("absence_months", sa.Integer(), nullable=True),
            ),
            (
                "is_probation_appraisal",
                sa.Column(
                    "is_probation_appraisal",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "confirmation_recommendation",
                sa.Column("confirmation_recommendation", sa.String(20), nullable=True),
            ),
            (
                "is_secondment_appraisal",
                sa.Column(
                    "is_secondment_appraisal",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "secondment_org_name",
                sa.Column("secondment_org_name", sa.String(200), nullable=True),
            ),
            (
                "parent_org_notified",
                sa.Column(
                    "parent_org_notified",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "parent_org_notified_date",
                sa.Column("parent_org_notified_date", sa.Date(), nullable=True),
            ),
            ("debrief_date", sa.Column("debrief_date", sa.Date(), nullable=True)),
            ("debrief_notes", sa.Column("debrief_notes", sa.Text(), nullable=True)),
            (
                "debrief_acknowledged",
                sa.Column(
                    "debrief_acknowledged",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            (
                "reward_nominated",
                sa.Column(
                    "reward_nominated",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            ),
            ("reward_type", sa.Column("reward_type", sa.String(50), nullable=True)),
            ("reward_notes", sa.Column("reward_notes", sa.Text(), nullable=True)),
        ]
        for col_name, col_def in appraisal_new_cols:
            _add_column_if_missing(inspector, "appraisal", "perf", col_name, col_def)

        # FK: appraisal.counter_signer_id → hr.employee
        existing_fks = {
            fk["name"] for fk in inspector.get_foreign_keys("appraisal", schema="perf")
        }
        appraisal_cols = {
            c["name"] for c in inspector.get_columns("appraisal", schema="perf")
        }

        if (
            "fk_appraisal_counter_signer" not in existing_fks
            and "counter_signer_id" in appraisal_cols
        ):
            op.create_foreign_key(
                "fk_appraisal_counter_signer",
                "appraisal",
                "employee",
                ["counter_signer_id"],
                ["employee_id"],
                source_schema="perf",
                referent_schema="hr",
            )

        if (
            "fk_appraisal_carryover" not in existing_fks
            and "carryover_source_id" in appraisal_cols
        ):
            op.create_foreign_key(
                "fk_appraisal_carryover",
                "appraisal",
                "appraisal",
                ["carryover_source_id"],
                ["appraisal_id"],
                source_schema="perf",
                referent_schema="perf",
            )

    # ------------------------------------------------------------------
    # 5. perf.appraisal_kra_score — 11 OHCSF fields
    # ------------------------------------------------------------------
    if inspector.has_table("appraisal_kra_score", schema="perf"):
        kra_score_new_cols = [
            (
                "target_description",
                sa.Column("target_description", sa.Text(), nullable=True),
            ),
            (
                "achievement_description",
                sa.Column("achievement_description", sa.Text(), nullable=True),
            ),
            ("evidence", sa.Column("evidence", sa.Text(), nullable=True)),
            (
                "outstanding_threshold",
                sa.Column("outstanding_threshold", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "excellent_threshold",
                sa.Column("excellent_threshold", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "good_threshold",
                sa.Column("good_threshold", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "fair_threshold",
                sa.Column("fair_threshold", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "poor_threshold",
                sa.Column("poor_threshold", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "actual_achievement",
                sa.Column("actual_achievement", sa.Numeric(12, 2), nullable=True),
            ),
            (
                "raw_score_percentage",
                sa.Column("raw_score_percentage", sa.Numeric(5, 2), nullable=True),
            ),
        ]
        for col_name, col_def in kra_score_new_cols:
            _add_column_if_missing(
                inspector, "appraisal_kra_score", "perf", col_name, col_def
            )

    # ------------------------------------------------------------------
    # 6. perf.kpi — institutional_objective_id
    # ------------------------------------------------------------------
    if inspector.has_table("kpi", schema="perf"):
        _add_column_if_missing(
            inspector,
            "kpi",
            "perf",
            "institutional_objective_id",
            sa.Column(
                "institutional_objective_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # kpi
    if inspector.has_table("kpi", schema="perf"):
        cols = {c["name"] for c in inspector.get_columns("kpi", schema="perf")}
        if "institutional_objective_id" in cols:
            op.drop_column("kpi", "institutional_objective_id", schema="perf")

    # appraisal_kra_score
    if inspector.has_table("appraisal_kra_score", schema="perf"):
        kra_score_cols = [
            "raw_score_percentage",
            "actual_achievement",
            "poor_threshold",
            "fair_threshold",
            "good_threshold",
            "excellent_threshold",
            "outstanding_threshold",
            "evidence",
            "achievement_description",
            "target_description",
        ]
        existing = {
            c["name"]
            for c in inspector.get_columns("appraisal_kra_score", schema="perf")
        }
        for col in kra_score_cols:
            if col in existing:
                op.drop_column("appraisal_kra_score", col, schema="perf")

    # appraisal FKs + columns
    if inspector.has_table("appraisal", schema="perf"):
        fks = {
            fk["name"] for fk in inspector.get_foreign_keys("appraisal", schema="perf")
        }
        if "fk_appraisal_carryover" in fks:
            op.drop_constraint(
                "fk_appraisal_carryover", "appraisal", schema="perf", type_="foreignkey"
            )
        if "fk_appraisal_counter_signer" in fks:
            op.drop_constraint(
                "fk_appraisal_counter_signer",
                "appraisal",
                schema="perf",
                type_="foreignkey",
            )

        appraisal_new_cols = [
            "reward_notes",
            "reward_type",
            "reward_nominated",
            "debrief_acknowledged",
            "debrief_notes",
            "debrief_date",
            "parent_org_notified_date",
            "parent_org_notified",
            "secondment_org_name",
            "is_secondment_appraisal",
            "confirmation_recommendation",
            "is_probation_appraisal",
            "absence_months",
            "carryover_source_id",
            "is_prior_year_carryover",
            "process_weighted_score",
            "competency_weighted_score",
            "objective_weighted_score",
            "process_comments",
            "process_final_rating",
            "process_manager_rating",
            "process_self_rating",
            "quarterly_rating",
            "is_quarterly",
            "committee_notes",
            "committee_decision",
            "committee_review_date",
            "counter_signer_comments",
            "counter_signer_date",
            "counter_signer_id",
        ]
        existing = {
            c["name"] for c in inspector.get_columns("appraisal", schema="perf")
        }
        for col in appraisal_new_cols:
            if col in existing:
                op.drop_column("appraisal", col, schema="perf")

    # appraisal_cycle FK + columns
    if inspector.has_table("appraisal_cycle", schema="perf"):
        fks = {
            fk["name"]
            for fk in inspector.get_foreign_keys("appraisal_cycle", schema="perf")
        }
        if "fk_cycle_parent" in fks:
            op.drop_constraint(
                "fk_cycle_parent", "appraisal_cycle", schema="perf", type_="foreignkey"
            )
        existing = {
            c["name"] for c in inspector.get_columns("appraisal_cycle", schema="perf")
        }
        for col in ["quarter", "parent_cycle_id", "cycle_type"]:
            if col in existing:
                op.drop_column("appraisal_cycle", col, schema="perf")

    # core_org.organization
    if inspector.has_table("organization", schema="core_org"):
        existing = {
            c["name"] for c in inspector.get_columns("organization", schema="core_org")
        }
        if "pms_ohcsf_enabled" in existing:
            op.drop_column("organization", "pms_ohcsf_enabled", schema="core_org")

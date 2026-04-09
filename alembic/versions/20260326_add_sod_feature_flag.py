"""Add require_segregation_of_duties feature flag.

Inserts the SoD flag into the feature_flag_registry table.
Default is False (single operator mode).

Revision ID: 20260326_sod_flag
Revises: 20260323_merge_invoice_purpose_heads
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "20260326_sod_flag"
down_revision = "20260323_merge_invoice_purpose_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO feature_flag_registry
                (flag_id, flag_key, label, description, category, status,
                 default_enabled, sort_order, created_at, updated_at)
            SELECT
                :flag_id, :flag_key, :label, :description, 'COMPLIANCE', 'ACTIVE',
                false, 10, :now, :now
            WHERE NOT EXISTS (
                SELECT 1
                FROM feature_flag_registry
                WHERE flag_key = :flag_key
            )
            """
        ).bindparams(
            flag_id=uuid.uuid4(),
            flag_key="require_segregation_of_duties",
            label="Segregation of Duties",
            description=(
                "Require different users to submit and approve journals, "
                "invoices, and payments. When disabled, the same user can "
                "perform all workflow steps."
            ),
            now=datetime.now(UTC),
        )
    )

    # Also seed into domain_settings so it shows in the features UI
    op.execute(
        sa.text(
            """
            INSERT INTO domain_settings
                (id, domain, key, value_type, value_json,
                 is_secret, is_active, scope,
                 organization_id, created_at, updated_at)
            VALUES
                (:setting_id, 'features', 'require_segregation_of_duties',
                 'boolean', 'false',
                 false, true, 'GLOBAL',
                 NULL, :now, :now)
            ON CONFLICT DO NOTHING
            """
        ).bindparams(
            setting_id=uuid.uuid4(),
            now=datetime.now(UTC),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM domain_settings "
            "WHERE domain = 'features' AND key = 'require_segregation_of_duties'"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM feature_flag_registry "
            "WHERE flag_key = 'require_segregation_of_duties'"
        )
    )

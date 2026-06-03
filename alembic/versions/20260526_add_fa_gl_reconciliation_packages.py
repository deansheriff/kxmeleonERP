"""Add fixed asset GL reconciliation approval packages.

Revision ID: 20260526_add_fa_gl_recon
Revises: fe8b31b22069
Create Date: 2026-05-26
"""

from alembic import op


revision = "20260526_add_fa_gl_recon"
down_revision = "fe8b31b22069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fa")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fa.gl_reconciliation_run (
            run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL
                REFERENCES core_org.organization(organization_id),
            as_of_date DATE NOT NULL,
            status VARCHAR(40) NOT NULL,
            currency_code VARCHAR(3),
            category_count INTEGER NOT NULL DEFAULT 0,
            asset_count INTEGER NOT NULL DEFAULT 0,
            total_variance_abs NUMERIC(20, 6) NOT NULL DEFAULT 0,
            nbv_variance NUMERIC(20, 6) NOT NULL DEFAULT 0,
            cost_variance NUMERIC(20, 6) NOT NULL DEFAULT 0,
            accumulated_depreciation_variance NUMERIC(20, 6) NOT NULL DEFAULT 0,
            approval_request_id UUID,
            proposed_journal_entry_id UUID,
            summary_payload JSONB,
            created_by_user_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fa.gl_reconciliation_exception (
            exception_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL
                REFERENCES fa.gl_reconciliation_run(run_id) ON DELETE CASCADE,
            organization_id UUID NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
            exception_type VARCHAR(50) NOT NULL,
            asset_account_id UUID,
            accumulated_depreciation_account_id UUID,
            category_codes TEXT,
            variance_amount NUMERIC(20, 6) NOT NULL,
            evidence_payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_fa_gl_recon_run_org_date
            ON fa.gl_reconciliation_run (organization_id, as_of_date);
        CREATE INDEX IF NOT EXISTS idx_fa_gl_recon_run_status
            ON fa.gl_reconciliation_run (organization_id, status);
        CREATE INDEX IF NOT EXISTS idx_fa_gl_recon_exception_run
            ON fa.gl_reconciliation_exception (run_id);
        CREATE INDEX IF NOT EXISTS idx_fa_gl_recon_exception_status
            ON fa.gl_reconciliation_exception (organization_id, status);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fa.gl_reconciliation_exception")
    op.execute("DROP TABLE IF EXISTS fa.gl_reconciliation_run")

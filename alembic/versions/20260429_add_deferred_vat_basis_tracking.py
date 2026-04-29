"""Add deferred VAT account metadata and tax basis tracking.

Revision ID: 20260429_deferred_vat_basis
Revises: 20260428_add_tax_control_evidence_table
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260429_deferred_vat_basis"
down_revision = "20260428_add_tax_control_evidence_table"
branch_labels = None
depends_on = None


tax_recognition_basis = postgresql.ENUM(
    "accrual",
    "cash",
    name="tax_recognition_basis",
)


ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFERRED_INPUT_VAT_CODE = "1455"


def upgrade() -> None:
    bind = op.get_bind()
    tax_recognition_basis.create(bind, checkfirst=True)

    op.add_column(
        "tax_transaction",
        sa.Column(
            "recognition_basis",
            sa.Enum(name="tax_recognition_basis"),
            nullable=False,
            server_default="accrual",
        ),
        schema="tax",
    )

    op.add_column(
        "account",
        sa.Column(
            "is_deferral",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema="gl",
    )
    op.add_column(
        "account",
        sa.Column(
            "deferral_pair_account_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        schema="gl",
    )
    op.create_foreign_key(
        "fk_gl_account_deferral_pair_account",
        "account",
        "account",
        ["deferral_pair_account_id"],
        ["account_id"],
        source_schema="gl",
        referent_schema="gl",
    )

    op.execute(
        f"""
        INSERT INTO gl.account (
            account_id, organization_id, category_id,
            account_code, account_name, description,
            account_type, normal_balance,
            is_multi_currency, is_active, is_posting_allowed, is_budgetable,
            is_reconciliation_required, is_cash_equivalent, is_financial_instrument,
            is_deferral, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            '{ORG_ID}'::uuid,
            (
                SELECT category_id
                FROM gl.account
                WHERE organization_id = '{ORG_ID}'::uuid
                  AND account_code = '1440'
                LIMIT 1
            ),
            '{DEFERRED_INPUT_VAT_CODE}',
            'Deferred Input VAT',
            'Input VAT incurred on supplier invoices but not yet paid. '
            'Recognised as recoverable only when cash is paid.',
            'POSTING',
            'DEBIT',
            false, true, true, true, false, false, false,
            true, now(), now()
        WHERE NOT EXISTS (
            SELECT 1
            FROM gl.account
            WHERE organization_id = '{ORG_ID}'::uuid
              AND account_code = '{DEFERRED_INPUT_VAT_CODE}'
        )
          AND EXISTS (
            SELECT 1
            FROM gl.account
            WHERE organization_id = '{ORG_ID}'::uuid
              AND account_code = '1440'
          )
        """
    )

    op.execute(
        f"""
        UPDATE gl.account
        SET is_deferral = true,
            deferral_pair_account_id = pair.account_id,
            updated_at = now()
        FROM gl.account pair
        WHERE account.organization_id = '{ORG_ID}'::uuid
          AND pair.organization_id = account.organization_id
          AND (
              (account.account_code = '2125' AND pair.account_code = '2120')
              OR
              (account.account_code = '{DEFERRED_INPUT_VAT_CODE}' AND pair.account_code = '1440')
          )
        """
    )
    op.execute(
        f"""
        UPDATE gl.account
        SET deferral_pair_account_id = pair.account_id,
            updated_at = now()
        FROM gl.account pair
        WHERE account.organization_id = '{ORG_ID}'::uuid
          AND pair.organization_id = account.organization_id
          AND (
              (account.account_code = '2120' AND pair.account_code = '2125')
              OR
              (account.account_code = '1440' AND pair.account_code = '{DEFERRED_INPUT_VAT_CODE}')
          )
        """
    )

    op.alter_column(
        "tax_transaction",
        "recognition_basis",
        schema="tax",
        server_default=None,
    )
    op.alter_column(
        "account",
        "is_deferral",
        schema="gl",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_gl_account_deferral_pair_account",
        "account",
        schema="gl",
        type_="foreignkey",
    )
    op.drop_column("account", "deferral_pair_account_id", schema="gl")
    op.drop_column("account", "is_deferral", schema="gl")
    op.drop_column("tax_transaction", "recognition_basis", schema="tax")
    tax_recognition_basis.drop(op.get_bind(), checkfirst=True)

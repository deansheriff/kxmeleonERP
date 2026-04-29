"""Repair deferred input VAT account code collision.

Revision ID: 20260429_fix_deferred_input_vat
Revises: 20260429_deferred_vat_basis
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op


revision = "20260429_fix_deferred_input_vat"
down_revision = "20260429_deferred_vat_basis"
branch_labels = None
depends_on = None


ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFERRED_INPUT_VAT_CODE = "1455"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE gl.account
        SET account_code = '{DEFERRED_INPUT_VAT_CODE}',
            updated_at = now()
        WHERE organization_id = '{ORG_ID}'::uuid
          AND account_code = '1450'
          AND account_name = 'Deferred Input VAT'
          AND NOT EXISTS (
              SELECT 1
              FROM gl.account existing
              WHERE existing.organization_id = '{ORG_ID}'::uuid
                AND existing.account_code = '{DEFERRED_INPUT_VAT_CODE}'
          )
        """
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
        SET is_deferral = false,
            deferral_pair_account_id = null,
            updated_at = now()
        WHERE organization_id = '{ORG_ID}'::uuid
          AND account_code = '1450'
          AND account_name <> 'Deferred Input VAT'
        """
    )

    op.execute(
        f"""
        UPDATE gl.account
        SET account_name = 'Deferred Input VAT',
            description = 'Input VAT incurred on supplier invoices but not yet paid. '
                          'Recognised as recoverable only when cash is paid.',
            is_deferral = true,
            deferral_pair_account_id = pair.account_id,
            updated_at = now()
        FROM gl.account pair
        WHERE account.organization_id = '{ORG_ID}'::uuid
          AND account.account_code = '{DEFERRED_INPUT_VAT_CODE}'
          AND pair.organization_id = account.organization_id
          AND pair.account_code = '1440'
        """
    )

    op.execute(
        f"""
        UPDATE gl.account
        SET deferral_pair_account_id = pair.account_id,
            updated_at = now()
        FROM gl.account pair
        WHERE account.organization_id = '{ORG_ID}'::uuid
          AND account.account_code = '1440'
          AND pair.organization_id = account.organization_id
          AND pair.account_code = '{DEFERRED_INPUT_VAT_CODE}'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE gl.account
        SET deferral_pair_account_id = pair.account_id,
            updated_at = now()
        FROM gl.account pair
        WHERE account.organization_id = '{ORG_ID}'::uuid
          AND account.account_code = '1440'
          AND pair.organization_id = account.organization_id
          AND pair.account_code = '1450'
        """
    )

    op.execute(
        f"""
        UPDATE gl.account
        SET is_deferral = false,
            deferral_pair_account_id = null,
            updated_at = now()
        WHERE organization_id = '{ORG_ID}'::uuid
          AND account_code = '{DEFERRED_INPUT_VAT_CODE}'
          AND account_name = 'Deferred Input VAT'
        """
    )

    op.execute(
        f"""
        UPDATE gl.account
        SET account_code = '1450',
            updated_at = now()
        WHERE organization_id = '{ORG_ID}'::uuid
          AND account_code = '{DEFERRED_INPUT_VAT_CODE}'
          AND account_name = 'Deferred Input VAT'
          AND NOT EXISTS (
              SELECT 1
              FROM gl.account existing
              WHERE existing.organization_id = '{ORG_ID}'::uuid
                AND existing.account_code = '1450'
          )
        """
    )

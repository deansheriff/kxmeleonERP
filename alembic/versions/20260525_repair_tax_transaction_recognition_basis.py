"""Repair missing tax transaction recognition basis column.

Revision ID: 20260525_repair_tax_txn_basis
Revises: 20260520_fa_asset_serial_unique
Create Date: 2026-05-25
"""

from __future__ import annotations

from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260525_repair_tax_txn_basis"
down_revision = "20260520_fa_asset_serial_unique"
branch_labels = None
depends_on = None


tax_recognition_basis = postgresql.ENUM(
    "accrual",
    "cash",
    name="tax_recognition_basis",
)


def upgrade() -> None:
    bind = op.get_bind()
    tax_recognition_basis.create(bind, checkfirst=True)
    op.execute(
        """
        ALTER TABLE tax.tax_transaction
        ADD COLUMN IF NOT EXISTS recognition_basis tax_recognition_basis
        NOT NULL DEFAULT 'accrual'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE tax.tax_transaction
        DROP COLUMN IF EXISTS recognition_basis
        """
    )
    tax_recognition_basis.drop(op.get_bind(), checkfirst=True)

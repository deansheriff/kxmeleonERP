"""Convert bank account tracking timestamps to dates.

Revision ID: 20260415_convert_bank_account_tracking_dates
Revises: 20260415_repair_mono_sync_tracking_drift
Create Date: 2026-04-15

``banking.bank_accounts.last_statement_date`` and
``last_reconciled_date`` are modeled and used as calendar dates. Some older
schema revisions created them as ``TIMESTAMPTZ``, which made Python callers
receive ``datetime`` values and crash when doing date arithmetic. Convert the
database columns to ``DATE`` to match the SQLAlchemy model.

Operational note: ``ALTER COLUMN ... TYPE date`` takes an ``ACCESS EXCLUSIVE``
lock on ``banking.bank_accounts`` while PostgreSQL rewrites the column. This
table is expected to be small, so the lock should be brief. If the same pattern
is needed for a large transactional table, use an expand/backfill/contract
migration instead of an in-place type change.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260415_convert_bank_account_tracking_dates"
down_revision = "20260415_repair_mono_sync_tracking_drift"
branch_labels = None
depends_on = None


def _column_type(
    conn: sa.engine.Connection,
    *,
    column_name: str,
) -> str | None:
    result = conn.execute(
        sa.text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'banking'
              AND table_name = 'bank_accounts'
              AND column_name = :column_name
            """
        ),
        {"column_name": column_name},
    )
    row = result.fetchone()
    return str(row.data_type) if row else None


def _alter_to_date(conn: sa.engine.Connection, column_name: str) -> None:
    if _column_type(conn, column_name=column_name) != "date":
        op.execute(
            sa.text(
                f"""
                ALTER TABLE banking.bank_accounts
                ALTER COLUMN {column_name} TYPE date
                USING {column_name}::date
                """
            )
        )


def _alter_to_timestamptz(conn: sa.engine.Connection, column_name: str) -> None:
    if _column_type(conn, column_name=column_name) == "date":
        op.execute(
            sa.text(
                f"""
                ALTER TABLE banking.bank_accounts
                ALTER COLUMN {column_name} TYPE timestamp with time zone
                USING {column_name}::timestamp with time zone
                """
            )
        )


def upgrade() -> None:
    conn = op.get_bind()
    _alter_to_date(conn, "last_statement_date")
    _alter_to_date(conn, "last_reconciled_date")


def downgrade() -> None:
    conn = op.get_bind()
    _alter_to_timestamptz(conn, "last_reconciled_date")
    _alter_to_timestamptz(conn, "last_statement_date")

"""Add Mono statement line idempotency constraint.

Revision ID: 20260415_add_mono_statement_line_uniqueness
Revises: 20260415_convert_bank_account_tracking_dates
Create Date: 2026-04-15

Mono imports use ``bank_statement_lines.transaction_id = 'mono_<provider id>'``
as the provider transaction identity. Enforce uniqueness for those imported
lines so concurrent webhook/manual syncs cannot duplicate the same Mono
transaction.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260415_add_mono_statement_line_uniqueness"
down_revision = "20260415_convert_bank_account_tracking_dates"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_banking_bank_statement_lines_mono_transaction_id"


def _index_exists(conn: sa.engine.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'banking'
              AND tablename = 'bank_statement_lines'
              AND indexname = :name
            """
        ),
        {"name": name},
    )
    return result.fetchone() is not None


def _ensure_unique_existing_mono_lines(conn: sa.engine.Connection) -> None:
    duplicate = conn.execute(
        sa.text(
            """
            SELECT transaction_id, count(*) AS duplicate_count
            FROM banking.bank_statement_lines
            WHERE transaction_id LIKE 'mono_%'
            GROUP BY transaction_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create unique Mono transaction index; duplicate "
            f"transaction_id {duplicate.transaction_id!r} exists on "
            f"{duplicate.duplicate_count} bank statement lines."
        )


def upgrade() -> None:
    conn = op.get_bind()
    _ensure_unique_existing_mono_lines(conn)

    if not _index_exists(conn, INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            "bank_statement_lines",
            ["transaction_id"],
            unique=True,
            schema="banking",
            postgresql_where=sa.text("transaction_id LIKE 'mono_%'"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, INDEX_NAME):
        op.drop_index(
            INDEX_NAME,
            table_name="bank_statement_lines",
            schema="banking",
        )

"""Add Mono sync tracking columns to bank_accounts.

Adds four columns to enable stateful, gap-free incremental Mono sync and
visible integration-health signals, while reusing the existing
``last_statement_date`` and ``last_statement_balance`` columns as the
source-agnostic data watermarks.

- ``mono_sync_from_date``   : cutover date (set at link time); Mono sync
                              never pulls transactions older than this, so
                              it doesn't collide with historical manual
                              CSV/PDF imports.
- ``mono_last_transaction_date`` : newest transaction date imported from Mono.
                              This is the sync cursor; the source-agnostic
                              ``last_statement_date`` may be moved by manual
                              statement imports and must not drive Mono sync.
- ``mono_last_synced_at``   : wall-clock time of the last *successful* Mono
                              API call. Advances on every successful sync,
                              even when Mono returned zero transactions, so
                              staleness is distinguishable from "haven't
                              tried in a while."
- ``mono_last_sync_error``  : most recent failure reason, cleared on next
                              success. NULL = healthy.
- ``mono_sync_buffer_days`` : rewind window (default 7) used by the
                              incremental sync to tolerate retroactive
                              posts and re-classifications.

Revision ID: 20260415_add_mono_sync_tracking
Revises: 20260414_add_inventory_serial_tables
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260415_add_mono_sync_tracking"
down_revision = "20260414_add_inventory_serial_tables"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("mono_sync_from_date", sa.Column("mono_sync_from_date", sa.Date(), nullable=True)),
    (
        "mono_last_transaction_date",
        sa.Column("mono_last_transaction_date", sa.Date(), nullable=True),
    ),
    (
        "mono_last_synced_at",
        sa.Column(
            "mono_last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    ),
    (
        "mono_last_sync_error",
        sa.Column("mono_last_sync_error", sa.Text(), nullable=True),
    ),
    (
        "mono_sync_buffer_days",
        sa.Column(
            "mono_sync_buffer_days",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    ),
)


def _column_exists(conn: sa.engine.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'banking' "
            "AND table_name = 'bank_accounts' "
            "AND column_name = :name"
        ),
        {"name": name},
    )
    return result.fetchone() is not None


def _index_exists(conn: sa.engine.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'banking' "
            "AND tablename = 'bank_accounts' "
            "AND indexname = :name"
        ),
        {"name": name},
    )
    return result.fetchone() is not None


def _backfill_existing_links(conn: sa.engine.Connection) -> None:
    """Seed Mono cursors for accounts already linked before this migration."""
    conn.execute(
        sa.text(
            """
            UPDATE banking.bank_accounts AS account
            SET mono_last_transaction_date = mono_lines.max_transaction_date
            FROM (
                SELECT
                    statement.bank_account_id,
                    max(line.transaction_date) AS max_transaction_date
                FROM banking.bank_statement_lines AS line
                JOIN banking.bank_statements AS statement
                    ON statement.statement_id = line.statement_id
                WHERE line.transaction_id LIKE 'mono_%'
                GROUP BY statement.bank_account_id
            ) AS mono_lines
            WHERE account.bank_account_id = mono_lines.bank_account_id
              AND account.mono_last_transaction_date IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE banking.bank_accounts
            SET mono_sync_from_date = CASE
                WHEN mono_last_transaction_date IS NOT NULL
                    THEN mono_last_transaction_date - COALESCE(mono_sync_buffer_days, 7)
                ELSE CURRENT_DATE - 90
            END
            WHERE mono_account_id IS NOT NULL
              AND mono_sync_from_date IS NULL
            """
        )
    )


def _ensure_unique_mono_account_ids(conn: sa.engine.Connection) -> None:
    duplicate = conn.execute(
        sa.text(
            """
            SELECT mono_account_id, count(*) AS duplicate_count
            FROM banking.bank_accounts
            WHERE mono_account_id IS NOT NULL
            GROUP BY mono_account_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create unique Mono account index; duplicate mono_account_id "
            f"{duplicate.mono_account_id!r} exists on {duplicate.duplicate_count} "
            "bank accounts."
        )


def upgrade() -> None:
    conn = op.get_bind()
    for name, column in _COLUMNS:
        if not _column_exists(conn, name):
            op.add_column("bank_accounts", column, schema="banking")
    _backfill_existing_links(conn)
    _ensure_unique_mono_account_ids(conn)
    if not _index_exists(conn, "uq_banking_bank_accounts_mono_account_id"):
        op.create_index(
            "uq_banking_bank_accounts_mono_account_id",
            "bank_accounts",
            ["mono_account_id"],
            unique=True,
            schema="banking",
            postgresql_where=sa.text("mono_account_id IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _index_exists(conn, "uq_banking_bank_accounts_mono_account_id"):
        op.drop_index(
            "uq_banking_bank_accounts_mono_account_id",
            table_name="bank_accounts",
            schema="banking",
        )
    for name, _ in reversed(_COLUMNS):
        if _column_exists(conn, name):
            op.drop_column("bank_accounts", name, schema="banking")

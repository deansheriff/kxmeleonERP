"""Repair Mono sync tracking migration drift.

Revision ID: 20260415_repair_mono_sync_tracking_drift
Revises: 20260415_add_mono_sync_tracking
Create Date: 2026-04-15

The original ``20260415_add_mono_sync_tracking`` revision was applied in
production before the Mono-specific cursor and unique provider-account
constraint were added to that file. This follow-up revision brings already
upgraded databases in line with the current model while remaining idempotent
for fresh databases that apply the amended parent revision first.

In other words, two databases can report the same parent Alembic revision while
having different physical schemas depending on whether they ran that revision
before or after it was amended. The duplicate-looking backfill and duplicate
checks here are intentional repair work for those drifted installs.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260415_repair_mono_sync_tracking_drift"
down_revision = "20260415_add_mono_sync_tracking"
branch_labels = None
depends_on = None


def _column_exists(
    conn: sa.engine.Connection,
    *,
    schema: str,
    table: str,
    name: str,
) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
              AND column_name = :name
            """
        ),
        {"schema": schema, "table": table, "name": name},
    )
    return result.fetchone() is not None


def _table_exists(conn: sa.engine.Connection, *, schema: str, table: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema
              AND table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    )
    return result.fetchone() is not None


def _index_exists(conn: sa.engine.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'banking'
              AND tablename = 'bank_accounts'
              AND indexname = :name
            """
        ),
        {"name": name},
    )
    return result.fetchone() is not None


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


def _backfill_existing_links(conn: sa.engine.Connection) -> None:
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


def _clear_legacy_mono_task_kwargs(conn: sa.engine.Connection) -> None:
    if not _table_exists(conn, schema="public", table="scheduled_tasks"):
        return
    conn.execute(
        sa.text(
            """
            UPDATE public.scheduled_tasks
            SET kwargs_json = '{}'::json
            WHERE task_name = 'app.tasks.finance.sync_mono_transactions'
              AND kwargs_json::text = '{"days_back": 3}'
            """
        )
    )


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(
        conn,
        schema="banking",
        table="bank_accounts",
        name="mono_last_transaction_date",
    ):
        op.add_column(
            "bank_accounts",
            sa.Column("mono_last_transaction_date", sa.Date(), nullable=True),
            schema="banking",
        )

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

    if _index_exists(conn, "ix_banking_bank_accounts_mono_account_id"):
        op.drop_index(
            "ix_banking_bank_accounts_mono_account_id",
            table_name="bank_accounts",
            schema="banking",
        )

    _clear_legacy_mono_task_kwargs(conn)


def downgrade() -> None:
    conn = op.get_bind()

    if not _index_exists(conn, "ix_banking_bank_accounts_mono_account_id"):
        op.create_index(
            "ix_banking_bank_accounts_mono_account_id",
            "bank_accounts",
            ["mono_account_id"],
            schema="banking",
        )

    if _index_exists(conn, "uq_banking_bank_accounts_mono_account_id"):
        op.drop_index(
            "uq_banking_bank_accounts_mono_account_id",
            table_name="bank_accounts",
            schema="banking",
        )

    if _column_exists(
        conn,
        schema="banking",
        table="bank_accounts",
        name="mono_last_transaction_date",
    ):
        op.drop_column(
            "bank_accounts",
            "mono_last_transaction_date",
            schema="banking",
        )

"""Add statement line number uniqueness.

Revision ID: 20260415_add_statement_line_number_uniqueness
Revises: 20260415_add_mono_statement_line_uniqueness
Create Date: 2026-04-15

Statement lines are ordered by ``line_number`` within a statement. Normalize
any pre-existing duplicate line numbers, then enforce that ordering key at
the database layer so concurrent syncs cannot allocate the same line number
inside a monthly Mono statement.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260415_add_statement_line_number_uniqueness"
down_revision = "20260415_add_mono_statement_line_uniqueness"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_bank_statement_line_number"


def _constraint_exists(conn: sa.engine.Connection, name: str) -> bool:
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE connamespace = 'banking'::regnamespace
              AND conrelid = 'banking.bank_statement_lines'::regclass
              AND conname = :name
            """
        ),
        {"name": name},
    )
    return result.fetchone() is not None


def _renumber_duplicate_line_numbers(conn: sa.engine.Connection) -> None:
    conn.execute(
        sa.text(
            """
            WITH duplicate_statements AS (
                SELECT statement_id
                FROM banking.bank_statement_lines
                GROUP BY statement_id, line_number
                HAVING count(*) > 1
            ),
            ordered_lines AS (
                SELECT
                    line_id,
                    row_number() OVER (
                        PARTITION BY statement_id
                        ORDER BY line_number, transaction_date, created_at, line_id
                    ) AS new_line_number
                FROM banking.bank_statement_lines
                WHERE statement_id IN (SELECT statement_id FROM duplicate_statements)
            )
            UPDATE banking.bank_statement_lines AS line
            SET line_number = ordered_lines.new_line_number
            FROM ordered_lines
            WHERE line.line_id = ordered_lines.line_id
              AND line.line_number <> ordered_lines.new_line_number
            """
        )
    )


def _ensure_unique_existing_line_numbers(conn: sa.engine.Connection) -> None:
    duplicate = conn.execute(
        sa.text(
            """
            SELECT statement_id, line_number, count(*) AS duplicate_count
            FROM banking.bank_statement_lines
            GROUP BY statement_id, line_number
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create statement line number constraint; duplicate "
            f"line_number {duplicate.line_number!r} exists on statement "
            f"{duplicate.statement_id} across {duplicate.duplicate_count} lines."
        )


def upgrade() -> None:
    conn = op.get_bind()
    _renumber_duplicate_line_numbers(conn)
    _ensure_unique_existing_line_numbers(conn)

    if not _constraint_exists(conn, CONSTRAINT_NAME):
        op.create_unique_constraint(
            CONSTRAINT_NAME,
            "bank_statement_lines",
            ["statement_id", "line_number"],
            schema="banking",
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _constraint_exists(conn, CONSTRAINT_NAME):
        op.drop_constraint(
            CONSTRAINT_NAME,
            "bank_statement_lines",
            schema="banking",
            type_="unique",
        )

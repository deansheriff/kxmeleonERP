"""Add updated_by_id to inventory return.

Revision ID: 20260410_add_inventory_return_updated_by
Revises: 20260409_add_inventory_return_table
Create Date: 2026-04-10
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260410_add_inventory_return_updated_by"
down_revision = "20260409_add_inventory_return_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_return", schema="inv"):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("inventory_return", schema="inv")
    }
    if "updated_by_id" not in columns:
        op.add_column(
            "inventory_return",
            sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            schema="inv",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("inventory_return", schema="inv"):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("inventory_return", schema="inv")
    }
    if "updated_by_id" in columns:
        op.drop_column("inventory_return", "updated_by_id", schema="inv")

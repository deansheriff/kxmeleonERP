"""Add inventory return workflow table.

Revision ID: 20260409_add_inventory_return_table
Revises: 20260409_add_material_request_transfer_destination
Create Date: 2026-04-09
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260409_add_inventory_return_table"
down_revision = "20260409_add_material_request_transfer_destination"
branch_labels = None
depends_on = None


def _column_has_unique_constraint(
    inspector: sa.Inspector, table_name: str, column_name: str, schema: str
) -> bool:
    for pk in [inspector.get_pk_constraint(table_name, schema=schema)]:
        constrained = pk.get("constrained_columns") or []
        if constrained == [column_name]:
            return True

    for unique in inspector.get_unique_constraints(table_name, schema=schema):
        constrained = unique.get("column_names") or []
        if constrained == [column_name]:
            return True

    for index in inspector.get_indexes(table_name, schema=schema):
        columns = index.get("column_names") or []
        if index.get("unique") and columns == [column_name]:
            return True

    return False


def _ensure_column_unique(
    bind: sa.Connection,
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    schema: str,
    constraint_name: str,
) -> None:
    if not inspector.has_table(table_name, schema=schema):
        return

    if _column_has_unique_constraint(inspector, table_name, column_name, schema):
        return

    duplicate_value = bind.execute(
        sa.text(
            f"""
            SELECT {column_name}
            FROM {schema}.{table_name}
            WHERE {column_name} IS NOT NULL
            GROUP BY {column_name}
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate_value is not None:
        raise RuntimeError(
            f"Cannot add unique constraint to {schema}.{table_name}.{column_name} because duplicate values exist."
        )

    op.create_unique_constraint(
        constraint_name,
        table_name,
        [column_name],
        schema=schema,
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, column_name, schema, constraint_name in [
        ("organization", "organization_id", "core_org", "uq_organization_org_id"),
        ("material_request", "request_id", "inv", "uq_material_request_request_id"),
        (
            "material_request_item",
            "item_id",
            "inv",
            "uq_material_request_item_item_id",
        ),
        ("item", "item_id", "inv", "uq_item_item_id"),
        ("warehouse", "warehouse_id", "inv", "uq_warehouse_warehouse_id"),
        ("inventory_lot", "lot_id", "inv", "uq_inventory_lot_lot_id"),
        (
            "inventory_transaction",
            "transaction_id",
            "inv",
            "uq_inventory_transaction_transaction_id",
        ),
    ]:
        _ensure_column_unique(
            bind,
            inspector,
            table_name,
            column_name,
            schema,
            constraint_name,
        )

    existing_enums = {enum["name"] for enum in inspector.get_enums(schema="inv")}
    if "inventory_return_mode" not in existing_enums:
        postgresql.ENUM(
            "MANUAL",
            "MATERIAL_REQUEST",
            name="inventory_return_mode",
            schema="inv",
        ).create(bind, checkfirst=True)

    if not inspector.has_table("inventory_return", schema="inv"):
        op.create_table(
            "inventory_return",
            sa.Column(
                "return_id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "organization_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("core_org.organization.organization_id"),
                nullable=False,
            ),
            sa.Column("return_number", sa.String(length=50), nullable=False),
            sa.Column(
                "return_mode",
                postgresql.ENUM(
                    "MANUAL",
                    "MATERIAL_REQUEST",
                    name="inventory_return_mode",
                    schema="inv",
                    create_type=False,
                ),
                nullable=False,
                server_default=sa.text("'MANUAL'"),
            ),
            sa.Column(
                "material_request_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.material_request.request_id"),
                nullable=True,
            ),
            sa.Column(
                "material_request_item_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.material_request_item.item_id"),
                nullable=True,
            ),
            sa.Column(
                "item_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.item.item_id"),
                nullable=False,
            ),
            sa.Column(
                "source_warehouse_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.warehouse.warehouse_id"),
                nullable=False,
            ),
            sa.Column(
                "destination_warehouse_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.warehouse.warehouse_id"),
                nullable=False,
            ),
            sa.Column("return_date", sa.Date(), nullable=False),
            sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
            sa.Column("uom", sa.String(length=20), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("reference", sa.String(length=100), nullable=True),
            sa.Column("remarks", sa.Text(), nullable=True),
            sa.Column(
                "lot_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.inventory_lot.lot_id"),
                nullable=True,
            ),
            sa.Column("lot_number", sa.String(length=50), nullable=True),
            sa.Column("serial_numbers", postgresql.ARRAY(sa.Text()), nullable=True),
            sa.Column(
                "source_transaction_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.inventory_transaction.transaction_id"),
                nullable=True,
            ),
            sa.Column(
                "posted_transaction_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("inv.inventory_transaction.transaction_id"),
                nullable=True,
            ),
            sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint(
                "organization_id",
                "return_number",
                name="uq_inventory_return_org_number",
            ),
            schema="inv",
        )
        op.create_index(
            "idx_inventory_return_org",
            "inventory_return",
            ["organization_id"],
            unique=False,
            schema="inv",
        )
        op.create_index(
            "idx_inventory_return_mode",
            "inventory_return",
            ["return_mode"],
            unique=False,
            schema="inv",
        )
        op.create_index(
            "idx_inventory_return_mr",
            "inventory_return",
            ["material_request_id"],
            unique=False,
            schema="inv",
        )
        op.create_index(
            "idx_inventory_return_item",
            "inventory_return",
            ["item_id"],
            unique=False,
            schema="inv",
        )
        op.create_index(
            "idx_inventory_return_return_date",
            "inventory_return",
            ["return_date"],
            unique=False,
            schema="inv",
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("inventory_return", schema="inv"):
        for index_name in [
            "idx_inventory_return_return_date",
            "idx_inventory_return_item",
            "idx_inventory_return_mr",
            "idx_inventory_return_mode",
            "idx_inventory_return_org",
        ]:
            op.drop_index(index_name, table_name="inventory_return", schema="inv")
        op.drop_table("inventory_return", schema="inv")

    existing_enums = {enum["name"] for enum in inspector.get_enums(schema="inv")}
    if "inventory_return_mode" in existing_enums:
        postgresql.ENUM(
            "MANUAL",
            "MATERIAL_REQUEST",
            name="inventory_return_mode",
            schema="inv",
        ).drop(bind, checkfirst=True)
